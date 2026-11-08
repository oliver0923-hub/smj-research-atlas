"""Versioned, starvation-free DOI/source ledger and bounded resumable OA cycle."""
import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from .article import PARSER_VERSION, digest, parse_article
from .core import now
from .network import OAFetcher, PolicyError, retry_seconds
from .research import EXTRACTOR_VERSION, extraction, validate_record, report as research_report
from .selection import safe_url

TERMINAL={'parsed','extraction_partial','extraction_complete_for_available_evidence','policy_blocked',
          'transient_failure','permanent_failure_for_url'}


def due(value,clock=None):
    return not value or datetime.fromisoformat(value.replace('Z','+00:00')) <= (clock or datetime.now(timezone.utc))


def later(seconds):
    return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()


def locations(entry,receipt=None):
    """No top-eight truncation. Keep each OA URL/version as an independent source."""
    found={}
    for loc in (entry or {}).get('oa_locations',[]):
        if not loc.get('is_oa') or not (loc.get('is_accepted') or loc.get('is_published') or loc.get('version') in {'acceptedVersion','publishedVersion'}):continue
        for kind in ['pdf_url','landing_page_url']:
            url=loc.get(kind)
            if url:found.setdefault(url,dict(url=url,version=loc.get('version'),license=loc.get('license'),kind=kind,rights_basis='provider_oa_accepted_or_published'))
    if receipt and receipt.get('accessible') and receipt.get('source_url'):
        url=receipt['source_url'];found.setdefault(url,dict(url=url,version=receipt.get('version'),license=receipt.get('license'),kind='previous_success',rights_basis=receipt.get('rights_basis','historical_openalex_oa_receipt')))
    return sorted(found.values(),key=lambda s:(s['kind'] not in {'pdf_url','previous_success'},any(x in s['url'] for x in ['wiley.com','ssrn.com','jstor.org']),s['url']))


def seed(papers,enrichment,receipts,old=(),control=None):
    entries={e['paper_id']:e for e in enrichment};prior={r['paper_id']:r for r in receipts}
    queue={r['paper_id']:r for r in old};stamp=now()
    corpus=digest('|'.join(sorted(p['paper_id'] for p in papers)))
    control=dict(control or dict(state='paused',cycle_id='cycle:'+stamp,first_seen_at=stamp))
    changed=control.get('corpus_fingerprint')!=corpus
    control.update(schema_version='4.0.0',corpus_fingerprint=corpus,updated_at=stamp,
                   parser_version=PARSER_VERSION,extractor_version=EXTRACTOR_VERSION,continuation_interval_hours=3)
    for p in sorted(papers,key=lambda p:p['paper_id']):
        pid=p['paper_id'];e=entries.get(pid);r=queue.get(pid)
        if not r:
            r=dict(paper_id=pid,doi=p['doi'],first_seen_at=stamp,updated_at=stamp,
                discovery_status='oa_location_found' if e and locations(e) else 'not_oa_found_yet' if e else 'discovery_pending',
                discovery_checked_at=e.get('retrieved_at') if e else None,discovery_attempts=[],
                queue_state='metadata_only',parse_state='not_yet_processed',extraction_state='not_yet_processed',
                sources=[],source_attempts=[],attempts_count=0,last_checked_at=None,next_retry_at=None,
                retry_reason=None,error_class=None,last_successful_evidence=None,visited=False)
            queue[pid]=r
        candidates=locations(e,prior.get(pid));known={s['url']:s for s in r['sources']}
        for candidate in candidates:
            if candidate['url'] not in known:
                blocked=not safe_url(candidate['url'])
                source=dict(candidate,source_id='src:'+digest(pid+'|'+candidate['url'])[:24],
                    state='policy_blocked' if blocked else 'fetch_pending',first_seen_at=stamp,updated_at=stamp,
                    attempts=[],attempts_count=0,last_checked_at=None,next_retry_at=None,cycle_attempted=None,
                    parser_version=None,extractor_version=None,source_fingerprint=None,
                    retry_reason=None,error_class='ssrf_unsafe_url' if blocked else None)
                if blocked:source['cycle_attempted']=control['cycle_id']
                r['sources'].append(source);changed=True
        r['oa_source_urls']=[s['url'] for s in r['sources']]
        r['candidate_version']=digest('|'.join(sorted(r['oa_source_urls'])))
        if r['sources'] and r['discovery_status']!='discovery_pending':r['discovery_status']='oa_location_found'
        if not r['visited']:r['queue_state']='fetch_pending' if r['sources'] else r['discovery_status']
    # Completed initial pass becomes discovery monitoring. A genuinely new DOI/source reopens it.
    if changed and control['state']=='cycle_complete':control['state']='running'
    return list(queue.values()),control


def plan(queue,control,limit=100):
    cycle=control['cycle_id'];rows=[]
    for paper in queue:
        for ordinal,source in enumerate(paper['sources']):
            first=source.get('cycle_attempted')!=cycle
            upgrade=source.get('state') in {'parsed','extraction_partial','extraction_complete_for_available_evidence'} and (source.get('parser_version')!=PARSER_VERSION or source.get('extractor_version')!=EXTRACTOR_VERSION)
            parser_retry=(source.get('error_class') or '').startswith('parse_or_extraction_failure:') and source.get('last_parser_attempt')!=PARSER_VERSION
            retry=source['state'] in {'transient_failure','permanent_failure_for_url','policy_blocked'} and due(source.get('next_retry_at')) and source.get('next_retry_at') is not None
            if (first or upgrade or parser_retry or retry) and (first or upgrade or parser_retry or due(source.get('next_retry_at'))):
                # Every paper's first candidate precedes its second, every unvisited candidate precedes retries/upgrades.
                attempt=sum(s.get('cycle_attempted')==cycle for s in paper['sources'])
                preferred=0 if source['kind'] in {'pdf_url','previous_success'} and not any(h in source['url'] for h in ['wiley.com','ssrn.com','jstor.org']) else 1
                rows.append((0 if first else 1,attempt+ordinal,paper['first_seen_at'],preferred,paper.get('last_checked_at') or '',paper['paper_id'],source['source_id'],paper,source))
    rows.sort(key=lambda r:r[:7])
    return [(r[7],r[8]) for r in rows[:limit]]


def progress(queue,control):
    cycle=control.get('cycle_id');sources=[s for p in queue for s in p['sources']]
    unvisited=[p for p in queue if not p.get('discovery_checked_at')]
    pending=[s for s in sources if s.get('cycle_attempted')!=cycle]
    # Empty eligible set alone cannot prove traversal; all DOI discovery receipts are required.
    complete=bool(queue) and not unvisited and not pending
    return dict(schema_version='4.0.0',generated_at=now(),state=control.get('state','not_initialized'),cycle_id=cycle,
        doi_total=len(queue),discovered=len(queue)-len(unvisited),discovery_unvisited=len(unvisited),
        with_oa_candidates=sum(bool(p['sources']) for p in queue),no_oa_found_yet=sum(not p['sources'] and bool(p.get('discovery_checked_at')) for p in queue),
        source_candidates=len(sources),source_attempted_this_cycle=sum(s.get('cycle_attempted')==cycle for s in sources),source_unvisited=len(pending),
        sources_with_http_attempt=sum(any(a.get('requests',0)>0 for a in s['attempts']) for s in sources),
        papers_with_http_200_body=sum(any(a.get('fetched_bytes',0)>0 for a in p['source_attempts']) for p in queue),
        sources_with_http_200_body=sum(any(a.get('fetched_bytes',0)>0 for a in s['attempts']) for s in sources),
        papers_attempted_this_cycle=sum(any(s.get('cycle_attempted')==cycle for s in p['sources']) for p in queue),
        parsed_papers=sum(bool(p.get('last_successful_evidence')) for p in queue),source_states=dict(Counter(s['state'] for s in sources)),
        failure_classes=dict(Counter(s['error_class'] for s in sources if s.get('error_class'))),
        retry_waiting=sum(bool(s.get('next_retry_at')) for s in sources),
        round_complete=complete,completion_definition='Every indexed DOI has a provider discovery receipt; every OA URL in this snapshot has a traceable attempt or policy reason',
        discovery_scope='OpenAlex indexed OA accepted/published locations and prior lawful receipts; not the entire internet',
        snapshot_doi_fingerprint=control.get('corpus_fingerprint'),next_continuation='cron every 3 hours while running; completed rounds enter low-frequency discovery monitoring',
        run_id=os.getenv('GITHUB_RUN_ID'),parser_version=PARSER_VERSION,extractor_version=EXTRACTOR_VERSION)


def classify_failure(status=None,error=None):
    text=str(error or '')
    if status==429 or 'retry_after' in text:return 'transient_failure','http_429_or_host_backoff',3600
    if status in {401,403}:return 'policy_blocked','http_'+str(status)+'_access_denied_not_assumed_paywall',60*86400
    if status in {404,410}:return 'permanent_failure_for_url','http_'+str(status),30*86400
    if status and status>=500:return 'transient_failure','http_'+str(status),3600
    if 'robots_' in text:return 'policy_blocked',text.split(':')[0],14*86400
    if 'ssrf_' in text:return 'policy_blocked','ssrf_blocked',None
    if 'identity' in text:return 'permanent_failure_for_url','article_identity_mismatch',30*86400
    if isinstance(error,(httpx.TimeoutException,httpx.NetworkError,OSError)):return 'transient_failure',type(error).__name__,3600
    if any(s in text for s in ['unsupported_document','not_article_html','not_enough_article_text']):return 'permanent_failure_for_url','not_article_document',30*86400
    return 'permanent_failure_for_url','parse_or_extraction_failure:'+type(error).__name__,14*86400


def save(queue,control,records):
    from .cli import DATA,write,lines
    write(DATA/'research_records.jsonl',lines(sorted(records.values(),key=lambda x:x['record_id'])))
    write(DATA/'crawl_queue.jsonl',lines(sorted(queue,key=lambda x:x['paper_id'])))
    write(DATA/'crawl_control.jsonl',lines([control]))
    write(DATA/'generated/crawl_progress.json',json.dumps(progress(queue,control),ensure_ascii=False,indent=2))


def discover(queue,control,fetcher,budget=4):
    """Anonymous DOI batches; an empty successful response is a discovery result, 429 isn't."""
    from .cli import DATA,read,write,lines
    from .enrich import FIELDS,abstract_text
    from .taxonomy import text_key
    papers={p['paper_id']:p for p in read('papers.jsonl')}
    enrichment={e['paper_id']:e for e in read('enrichment.jsonl')}
    pending=sorted((p for p in queue if not p.get('discovery_checked_at')),key=lambda p:p['paper_id'])
    tax=json.loads((DATA/'ontology.yaml').read_text(encoding='utf-8'))
    for offset in range(0,min(len(pending),budget*30),30):
        batch=pending[offset:offset+30]
        params={'filter':'doi:'+'|'.join('https://doi.org/'+p['doi'] for p in batch),'select':FIELDS,'per_page':100}
        # Fixed trusted API URL, no bearer tokens; pagination is never needed for a DOI batch.
        if fetcher.requests>=fetcher.max_requests:break
        fetcher.requests+=1
        response=fetcher.client.get('https://api.openalex.org/works',params=params)
        if response.status_code!=200:
            for p in batch:p['retry_reason']='discovery_http_'+str(response.status_code);p['next_retry_at']=later(retry_seconds(response.headers.get('retry-after')))
            break
        results={(e.get('doi') or '').lower().removeprefix('https://doi.org/'):e for e in response.json().get('results',[])}
        for p in batch:
            raw=results.get(p['doi'].lower());stamp=now()
            p['discovery_checked_at']=stamp;p['discovery_attempts'].append(dict(at=stamp,provider='OpenAlex',http_status=200,matched=bool(raw)))
            if raw:
                abstract=abstract_text(raw.get('abstract_inverted_index'));normalized=' '+text_key(abstract)+' '
                locs=list(raw.get('locations') or [])+[v for k in ['best_oa_location','primary_location'] if (v:=raw.get(k))]
                enrichment[p['paper_id']]=dict(paper_id=p['paper_id'],openalex_id=raw['id'],source_url=raw['id'],retrieved_at=stamp,
                    abstract_available=bool(abstract),abstract_hash=digest(abstract) if abstract else None,
                    abstract_phrase_hits=[n['id'] for n in tax['nodes'] if n['level'] in {'research_topic','theory'} and any(' '+text_key(s)+' ' in normalized for s in n.get('match_phrases',[]))],
                    oa_locations=[l for l in locs if l.get('is_oa')],citation_count=raw.get('cited_by_count'),is_retracted=raw.get('is_retracted'))
            p['discovery_status']='oa_location_found' if raw and locations(enrichment[p['paper_id']]) else 'not_oa_found_yet'
            p['next_retry_at']=later(30*86400);p['retry_reason']='scheduled_provider_rediscovery'
        write(DATA/'enrichment.jsonl',lines(list(enrichment.values())))
    return seed(list(papers.values()),list(enrichment.values()),read('content_receipts.jsonl'),queue,control)


def tick(command='continue_oa',max_sources=180,max_requests=450,seconds=600,persist=False,fetcher=None):
    from .cli import DATA,ROOT,read,write,lines
    queue,control=seed(read('papers.jsonl'),read('enrichment.jsonl'),read('content_receipts.jsonl'),read('crawl_queue.jsonl'),next(iter(read('crawl_control.jsonl')),None))
    records={r['record_id']:r for r in read('research_records.jsonl')}
    events=read('crawl_events.jsonl');quarantine=read('research_quarantine.jsonl')
    if command=='pause_oa':control['state']='paused'
    elif command in {'exhaust_oa','resume_oa'}:control['state']='running'
    elif command=='restart_oa':
        control.update(state='running',cycle_id='cycle:'+now(),completed_at=None)
    elif control['state']=='cycle_complete' and due(control.get('next_discovery_at')):
        # Low-frequency provider refresh reopens discovery without re-fetching every known URL.
        for p in queue:
            if due(p.get('next_retry_at')):p['discovery_checked_at']=None
        control['state']='running'
    control['last_run_id']=os.getenv('GITHUB_RUN_ID','local');control['last_command']=command
    save(queue,control,records)
    if control['state']!='running':
        if persist:persist_snapshot()
        return progress(queue,control)
    fetcher=fetcher or OAFetcher();fetcher.max_requests=max_requests
    started=time.monotonic();processed=0;last_persist=started
    try:
        queue,control=discover(queue,control,fetcher)
        save(queue,control,records)
        papers={p['paper_id']:p for p in read('papers.jsonl')}
        for paper,source in plan(queue,control,max_sources):
            if time.monotonic()-started>=seconds or fetcher.requests>=max_requests:break
            before=fetcher.requests;stamp=now()
            attempt=dict(at=stamp,run_id=control['last_run_id'],source_version=paper['candidate_version'],url=source['url'],http_status=None)
            try:
                response,chain=fetcher.fetch(source['url']);attempt.update(http_status=response.status_code,redirect_chain=chain)
                if response.status_code!=200:
                    state,error,cooldown=classify_failure(status=response.status_code)
                    source.update(state=state,error_class=error,next_retry_at=later(retry_seconds(response.headers.get('retry-after'))) if response.status_code==429 else later(cooldown) if cooldown else None)
                else:
                    if 'html' in response.headers.get('content-type',''):
                        from bs4 import BeautifulSoup
                        from urllib.parse import urljoin
                        soup=BeautifulSoup(response.content,'html.parser')
                        links=[m.get('content') for m in soup.select('meta[name="citation_pdf_url"]')]
                        links += [a.get('href') for a in soup.find_all('a',href=True) if re.search(r'\.pdf(?:$|[?#])|/bitstreams?/[^ ]+/download',a['href'],re.I)]
                        for href in dict.fromkeys(links):
                            if not href:continue
                            url=urljoin(str(response.url),href)
                            if any(s['url']==url for s in paper['sources']):continue
                            blocked=not safe_url(url)
                            paper['sources'].append(dict(url=url,version=source.get('version'),license=source.get('license'),kind='pdf_url',rights_basis='linked_from_indexed_oa_location',parent_url=source['url'],source_id='src:'+digest(paper['paper_id']+'|'+url)[:24],state='policy_blocked' if blocked else 'fetch_pending',first_seen_at=stamp,updated_at=stamp,attempts=[],attempts_count=0,last_checked_at=None,next_retry_at=None,cycle_attempted=control['cycle_id'] if blocked else None,parser_version=None,extractor_version=None,source_fingerprint=None,retry_reason=None,error_class='ssrf_unsafe_url' if blocked else None))
                            paper['oa_source_urls'].append(url)
                        paper['candidate_version']=digest('|'.join(sorted(paper['oa_source_urls'])))
                    receipt=dict(source_url=str(response.url),source_hash=digest(response.content),checked_at=stamp,accessible=True)
                    attempt['fetched_bytes']=len(response.content);source['state']='fetched'
                    private_source=ROOT/'.cache/source_documents'/(digest(response.content)+'.bin')
                    private_source.parent.mkdir(parents=True,exist_ok=True);private_source.write_bytes(response.content)
                    rawpath=ROOT/'.cache/pdfs'/(digest(paper['paper_id'])[:16]+'.pdf')
                    if response.content.startswith(b'%PDF'):
                        rawpath.parent.mkdir(parents=True,exist_ok=True);rawpath.write_bytes(response.content)
                    source['last_parser_attempt']=PARSER_VERSION
                    doc=parse_article(papers[paper['paper_id']],response.content,response.headers.get('content-type',''),receipt)
                    source['state']='parsed';record=extraction(doc);validate_record(record)
                    record.update(record_id=paper['paper_id']+'@'+doc.source_hash[:16],extracted_at=stamp,run_id=control['last_run_id'])
                    records[record['record_id']]=record
                    cache=ROOT/'.cache/articles'/ (digest(paper['paper_id'])[:16]+'-'+doc.source_hash[:12]+'.json')
                    write(cache,json.dumps(doc.__dict__,ensure_ascii=False))
                    source.update(state=record['extraction_state'],error_class=None,source_fingerprint=doc.source_hash,parser_version=PARSER_VERSION,extractor_version=EXTRACTOR_VERSION,next_retry_at=None,record_id=record['record_id'])
                    # Prefer most field evidence, retain all source versions and the previous good record.
                    old=records.get((paper.get('last_successful_evidence') or {}).get('record_id'))
                    if old is None or len(record['evidence'])>=len(old['evidence']):
                        paper['last_successful_evidence']=dict(record_id=record['record_id'],source_hash=doc.source_hash,source_url=doc.source_url,at=stamp)
                    attempt.update(parsed=True,record_id=record['record_id'],fields_validated=True)
            except Exception as exc:
                if isinstance(exc,PolicyError) and str(exc)=='global_request_budget':break
                state,error,cooldown=classify_failure(error=exc)
                source.update(state=state,error_class=error,next_retry_at=later(cooldown) if cooldown else None)
                attempt.update(error_class=error,exception_type=type(exc).__name__)
                if state=='permanent_failure_for_url' and 'extraction' in error:
                    quarantine.append(dict(paper_id=paper['paper_id'],url=source['url'],at=stamp,error_class=error,retained_previous=bool(paper.get('last_successful_evidence'))))
            source['attempts_count']+=1;source['last_checked_at']=stamp;source['updated_at']=stamp
            source['cycle_attempted']=control['cycle_id'];attempt['requests']=fetcher.requests-before
            source['attempts'].append(attempt);source['attempts']=source['attempts'][-12:]
            paper['source_attempts'].append(dict(source_id=source['source_id'],**attempt));paper['source_attempts']=paper['source_attempts'][-40:]
            paper.update(last_checked_at=stamp,updated_at=stamp,visited=True,attempts_count=paper['attempts_count']+1,
                queue_state=source['state'],parse_state='parsed' if paper.get('last_successful_evidence') else source['state'],
                extraction_state=source['state'] if attempt.get('fields_validated') else paper['extraction_state'])
            processed+=1;save(queue,control,records)
            if persist and (processed%15==0 or time.monotonic()-last_persist>50):
                persist_snapshot();last_persist=time.monotonic()
        result=progress(queue,control)
        if result['round_complete']:
            control.update(state='cycle_complete',completed_at=now(),next_discovery_at=later(7*86400))
        control.update(last_finished_at=now(),last_source_count=processed,last_requests=fetcher.requests)
        result=progress(queue,control);events.append(dict(at=now(),run_id=control['last_run_id'],sources_processed=processed,requests=fetcher.requests,**{k:result[k] for k in ['cycle_id','round_complete','discovered','source_unvisited']}))
        save(queue,control,records);write(DATA/'crawl_events.jsonl',lines(events[-200:]));write(DATA/'research_quarantine.jsonl',lines(quarantine[-100:]))
        if persist:persist_snapshot()
        return dict(result,processed_this_run=processed,requests_this_run=fetcher.requests)
    finally:
        fetcher.close()


def persist_snapshot():
    """Commit verified progress before website tests/deployment; never force-push."""
    import subprocess
    from .release import snapshot
    from .cli import ROOT
    snapshot()
    if os.getenv('GITHUB_ACTIONS')!='true':return
    def git(*args,input=None,check=True):
        return subprocess.run(['git',*args],cwd=ROOT,input=input,capture_output=True,text=True,check=check).stdout.strip()
    git('config','user.name','SMJ Atlas data bot');git('config','user.email','atlas-bot@users.noreply.github.com')
    blob=git('hash-object','-w','data/live_state.json.gz')
    entries=f'100644 blob {blob}\tlive_state.json.gz\n'
    if (ROOT/'data/generated/crawl_progress.json').exists():
        progress_blob=git('hash-object','-w','data/generated/crawl_progress.json')
        entries+=f'100644 blob {progress_blob}\tcrawl_progress.json\n'
    sub=git('mktree',input=entries)
    tree=git('mktree',input=f'040000 tree {sub}\tdata\n')
    parent=git('rev-parse','--verify','origin/atlas-data',check=False)
    args=['commit-tree',tree]+(['-p',parent] if parent else [])
    commit=git(*args,input='Verified crawl checkpoint '+os.getenv('GITHUB_RUN_ID','')+'\n')
    git('push','origin',commit+':refs/heads/atlas-data')
    git('update-ref','refs/remotes/origin/atlas-data',commit)
    if os.getenv('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'],'a',encoding='utf-8') as f:f.write('PAGES_BUILD_VERSION='+commit+'\n')
    return commit


def active_records(records,queue=()):
    preferred={p['paper_id']:p.get('last_successful_evidence',{}).get('record_id') for p in queue if p.get('last_successful_evidence')}
    selected={}
    for r in records:
        old=selected.get(r['paper_id'])
        if old is None or preferred.get(r['paper_id'])==r['record_id'] or (preferred.get(r['paper_id'])!=old['record_id'] and len(r['evidence'])>len(old['evidence'])):selected[r['paper_id']]=r
    return list(selected.values())


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['exhaust_oa','continue_oa','pause_oa','resume_oa','restart_oa','status','persist']);p.add_argument('--sources',type=int,default=180);p.add_argument('--requests',type=int,default=450);p.add_argument('--seconds',type=int,default=600);p.add_argument('--persist',action='store_true');a=p.parse_args()
    if a.command=='persist':
        print(json.dumps({'commit':persist_snapshot()}));return
    if a.command=='status':
        from .cli import read
        print(json.dumps(progress(read('crawl_queue.jsonl'),next(iter(read('crawl_control.jsonl')),{}))))
    else:print(json.dumps(tick(a.command,a.sources,a.requests,a.seconds,a.persist),ensure_ascii=False))

if __name__=='__main__':main()
