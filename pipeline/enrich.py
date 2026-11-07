"""Budgeted OpenAlex discovery and lawful transient OA acquisition (no PDFs committed)."""
import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .cli import DATA, ROOT, read, write, lines
from .core import ISSNS, doi_key, now

USER_AGENT='SMJResearchAtlas/3.0 (scholarly metadata and lawful OA evidence)'
FIELDS='id,doi,title,publication_year,primary_location,best_oa_location,locations,abstract_inverted_index,cited_by_count,type,open_access,topics,is_retracted'
CACHE=ROOT/'.cache'

def get(client,url,params=None,attempts=3):
    for attempt in range(attempts):
        response=client.get(url,params=params)
        if response.status_code==429 or response.status_code>=500:
            if attempt==attempts-1:response.raise_for_status()
            time.sleep(min(15,2**attempt));continue
        response.raise_for_status();return response

def abstract_text(index):
    pairs=[(i,word) for word,positions in (index or {}).items() for i in positions]
    return ' '.join(w for _,w in sorted(pairs))

def harvest(max_pages=50,dry_run=False):
    papers={p['doi']:p for p in read('papers.jsonl')}
    existing={p['paper_id']:p for p in read('enrichment.jsonl')}
    status={'source':'OpenAlex','started_at':now(),'budget_pages':max_pages,'status':'running','requests':0,'matched':0,'errors':[]}
    if dry_run:return dict(status,status='dry_run',potential_papers=len(papers))
    CACHE.mkdir(exist_ok=True);(CACHE/'abstracts').mkdir(exist_ok=True)
    checkpoint=DATA/'staging/openalex_checkpoint.json'
    state=json.loads(checkpoint.read_text()) if checkpoint.exists() else {'cursor':'*'}
    batch_ids=sorted(papers)
    api_token=os.getenv('OPENALEX_API_KEY')
    if not api_token and 'batch' not in state:state={'batch':0}
    with httpx.Client(timeout=50,follow_redirects=True,headers={'User-Agent':USER_AGENT}) as client:
        for _ in range(max_pages):
            try:
                params={'filter':'primary_location.source.issn:1097-0266','per_page':100,'select':FIELDS}
                if api_token:params.update(cursor=state.get('cursor','*'),api_key=api_token)
                else:
                    batch=batch_ids[state['batch']:state['batch']+40]
                    if not batch:status['status']='complete';checkpoint.unlink(missing_ok=True);break
                    params['filter']='doi:'+'|'.join(batch)
                payload=get(client,'https://api.openalex.org/works',params).json()
            except Exception as exc:
                status['errors'].append({'kind':type(exc).__name__,'http_status':getattr(getattr(exc,'response',None),'status_code',None)});status['status']='partial_failure';break
            status['requests']+=1
            for raw in payload.get('results',[]):
                try:doi=doi_key(raw.get('doi') or '')
                except ValueError:continue
                primary=(raw.get('primary_location') or {}).get('source') or {}
                if doi not in papers or not ISSNS.intersection(primary.get('issn') or []):continue
                paper=papers[doi];abstract=abstract_text(raw.get('abstract_inverted_index'))
                key=hashlib.sha256(paper['paper_id'].encode()).hexdigest()[:16]
                if abstract:write(CACHE/'abstracts'/(key+'.txt'),abstract)
                tax=json.loads((DATA/'ontology.yaml').read_text(encoding='utf-8'))
                from .taxonomy import text_key
                normalized=' '+text_key(abstract)+' '
                features=[n['id'] for n in tax['nodes'] if n['level'] in {'research_topic','theory'} and any(' '+text_key(phrase)+' ' in normalized for phrase in n.get('match_phrases',[]))]
                locations=[l for l in raw.get('locations',[]) if l.get('is_oa') and (l.get('is_accepted') or l.get('is_published'))]
                entry=dict(paper_id=paper['paper_id'],openalex_id=raw['id'],citation_count=raw.get('cited_by_count'),citation_count_asof=now()[:10],
                    external_topics=raw.get('topics',[]),openalex_type=raw.get('type'),is_retracted=raw.get('is_retracted'),
                    abstract_available=bool(abstract),abstract_phrase_hits=features,abstract_feature_method='allowed_phrase_occurrence_v3',abstract_hash=hashlib.sha256(abstract.encode()).hexdigest() if abstract else None,
                    abstract_license='OpenAlex metadata CC0; full abstract is not redistributed by Atlas',
                    oa_locations=locations,oa_url=(raw.get('best_oa_location') or {}).get('landing_page_url'),source_url=raw['id'],retrieved_at=now(),
                    inference_origin='openalex_metadata',evidence_grade='E1_abstract' if abstract else 'E0_metadata')
                old=existing.get(paper['paper_id'])
                if old and {k:v for k,v in old.items() if k!='retrieved_at'}=={k:v for k,v in entry.items() if k!='retrieved_at'}:entry=old
                existing[paper['paper_id']]=entry;status['matched']+=1
            write(DATA/'enrichment.jsonl',lines(sorted(existing.values(),key=lambda p:p['paper_id'])))
            if not os.getenv('OPENALEX_API_KEY'):
                state['batch']+=40;write(checkpoint,json.dumps(state));time.sleep(.4);continue
            nxt=payload.get('meta',{}).get('next_cursor')
            if not nxt or not payload.get('results'):
                status['status']='complete';checkpoint.unlink(missing_ok=True);break
            state['cursor']=nxt;write(checkpoint,json.dumps(state));time.sleep(.5)
        else:status['status']='budget_reached'
    status['finished_at']=now();write(DATA/'enrichment_state.json',json.dumps(status,ensure_ascii=False,indent=2));return status

def robots_allowed(client,url,cache):
    host=urlparse(url).netloc
    if host not in cache:
        try:
            r=client.get('https://'+host+'/robots.txt')
            if r.status_code in {401,403,429}:
                cache[host]=False
            elif r.status_code==404:cache[host]=True
            elif r.is_success:
                parser=RobotFileParser();parser.parse(r.text.splitlines());cache[host]=parser
            else:cache[host]=False
        except httpx.HTTPError:cache[host]=False
    rule=cache[host]
    return rule if isinstance(rule,bool) else rule.can_fetch(USER_AGENT,url)

def parse_document(content,content_type):
    if content.startswith(b'%PDF'):
        import fitz
        with fitz.open(stream=content,filetype='pdf') as doc:
            return [{'page':i+1,'text':page.get_text('text')} for i,page in enumerate(doc)],'pymupdf-v1'
    if 'html' in content_type:
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(content,'html.parser')
        for el in soup(['script','style','nav','header','footer']):el.decompose()
        body=soup.find('article') or soup.find('main') or soup.body or soup
        text=body.get_text(' ',strip=True)
        if soup.find('article') and len(text)>15000 and any(re.search(r'method|measure|data',h.get_text(),re.I) for h in soup.find_all(['h2','h3','h4'])):return [{'page':None,'text':text}],'beautifulsoup-v1'
    raise ValueError('Not an inspectable full-text document')

def acquire(max_papers=40,dry_run=False):
    from .evidence import extract_variables
    papers={p['paper_id']:p for p in read('papers.jsonl')}
    enrich=read('enrichment.jsonl');old={r['paper_id']:r for r in read('content_receipts.jsonl')}
    variables={v['variable_id']:v for v in read('variables.jsonl')};runs=read('extraction_runs.jsonl')
    candidates=[e for e in enrich if e.get('oa_locations') and e['paper_id'] in papers and not old.get(e['paper_id'],{}).get('accessible')]
    candidates.sort(key=lambda e:(not any(l.get('pdf_url') and not any(h in l['pdf_url'] for h in ['wiley','ssrn','jstor']) for l in e['oa_locations']),e['paper_id'] in old))
    # Round-robin title-derived domains ensures the budget is not only the most-cited stream.
    from .taxonomy import suggest_assignments
    tax=json.loads((DATA/'ontology.yaml').read_text(encoding='utf-8'))
    bins={};unassigned=[]
    for e in candidates:
        tags=[a['term_id'] for a in suggest_assignments([papers[e['paper_id']]],tax) if a['term_id'].startswith('SMS-')]
        (bins.setdefault(tags[0],[]) if tags else unassigned).append(e)
    ordered=[]
    while any(bins.values()):
        for group in bins.values():
            if group:ordered.append(group.pop(0))
    ordered+=unassigned
    if dry_run:return {'status':'dry_run','candidate_papers':len(ordered),'budget':max_papers,'provider':'deterministic','paid_api_calls':0}
    (CACHE/'fulltext').mkdir(parents=True,exist_ok=True)
    robots={};processed=0
    with httpx.Client(timeout=25,follow_redirects=True,headers={'User-Agent':USER_AGENT}) as client:
        for e in ordered[:max_papers]:
            paper=papers[e['paper_id']];key=hashlib.sha256(paper['paper_id'].encode()).hexdigest()[:16]
            receipt=dict(paper_id=paper['paper_id'],accessible=False,checked_at=now(),source_url=None,license=None,source_hash=None,parser_version=None,failures=[],missing_reason='no_accessible_lawful_fulltext')
            locs=sorted(e['oa_locations'],key=lambda l:('wiley.com' in (l.get('pdf_url') or l.get('landing_page_url') or ''),not bool(l.get('pdf_url'))))
            for loc in locs[:4]:
                url=loc.get('pdf_url') or loc.get('landing_page_url')
                if not url or urlparse(url).scheme!='https':continue
                # OA metadata is an access lead, not a right to bypass publisher controls.
                try:
                    if not robots_allowed(client,url,robots):raise ValueError('robots_disallowed_or_unavailable')
                    response=get(client,url,attempts=1)
                    if len(response.content)>25_000_000:raise ValueError('document_budget_exceeded')
                    pages,parser=parse_document(response.content,response.headers.get('content-type',''))
                    text=' '.join(p['text'] for p in pages)
                    words=set(re.findall(r'[a-z]{4,}',paper['title'].lower()));begin=set(re.findall(r'[a-z]{4,}',text[:12000].lower()))
                    families=[a.split()[-1].lower() for a in paper.get('authors',[]) if a.split()]
                    if not words or len(words&begin)/len(words)<.85 or not any(f in text[:12000].lower() for f in families):raise ValueError('title_author_identity_mismatch')
                    if len(text)<15000:raise ValueError('fulltext_too_short')
                    receipt.update(accessible=True,source_url=str(response.url),license=loc.get('license'),version=loc.get('version'),rights_basis='OpenAlex OA accepted/published source; transient reading and short evidence only',source_hash=hashlib.sha256(response.content).hexdigest(),text_hash=hashlib.sha256(text.encode()).hexdigest(),parser_version=parser,missing_reason=None,page_count=len(pages))
                    write(CACHE/'fulltext'/(key+'.json'),json.dumps({'pages':pages,'receipt':receipt},ensure_ascii=False))
                    records=extract_variables(paper,pages,receipt)
                    for v in records:
                        if v['variable_id'] not in variables or not variables[v['variable_id']].get('human_reviewer'):variables[v['variable_id']]=v
                    break
                except Exception as exc:
                    receipt['failures'].append({'url':url,'reason':type(exc).__name__+':'+str(exc)[:160]})
                time.sleep(.4)
            old[e['paper_id']]=receipt;processed+=1
            runs.append(dict(run_id='run:'+key+':'+receipt['checked_at'],paper_id=e['paper_id'],at=receipt['checked_at'],parser=receipt.get('parser_version'),status='accessible' if receipt['accessible'] else 'insufficient_evidence',provider='deterministic',paid_api_calls=0,source_url=receipt['source_url']))
            write(DATA/'content_receipts.jsonl',lines(sorted(old.values(),key=lambda p:p['paper_id'])))
            write(DATA/'variables.jsonl',lines(sorted(variables.values(),key=lambda p:p['variable_id'])))
            write(DATA/'extraction_runs.jsonl',lines(runs))
            print(json.dumps({'processed':processed,'paper_id':e['paper_id'],'accessible':receipt['accessible'],'total_variables':len(variables)}),flush=True)
    return {'processed':processed,'accessible':sum(r['accessible'] for r in old.values()),'variables':len(variables)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['metadata','fulltext']);parser.add_argument('--budget',type=int,default=40);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    print(json.dumps(harvest(args.budget,args.dry_run) if args.command=='metadata' else acquire(args.budget,args.dry_run),ensure_ascii=False))
if __name__=='__main__':main()
