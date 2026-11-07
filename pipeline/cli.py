"""Run with python -m pipeline.cli sync|build|validate."""
import argparse, json, os, random, time, hashlib, gzip
from pathlib import Path
from datetime import datetime, timedelta, timezone
import httpx, yaml
from .core import display_text, normalize, upsert, now, Paper, Variable
from .taxonomy import validate_taxonomy, suggest_assignments, emerging_topics, enrich_papers, Assignment
from .classify import classify
from .analytics import derive, coverage, research_graph, article_kind, gap_candidates
from .evidence import OperationalVariable
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data'
def read(name):
    p=DATA/name
    if name=='papers.jsonl' and not p.exists() and (DATA/'bootstrap_papers.jsonl.gz').exists():
        return [json.loads(s) for s in gzip.decompress((DATA/'bootstrap_papers.jsonl.gz').read_bytes()).decode('utf-8').splitlines() if s.strip()]
    return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()] if p.exists() else []
def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(value,encoding='utf-8'); tmp.replace(path)
def lines(rows): return ''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows)
def request(client,url,params):
    for attempt in range(5):
        try:
            r=client.get(url,params=params)
            if r.status_code==429 or r.status_code>=500:
                if attempt==4: r.raise_for_status()
                time.sleep(min(30,2**attempt+random.random())); continue
            r.raise_for_status(); return r.json()['message']
        except httpx.TransportError:
            if attempt==4: raise
            time.sleep(2**attempt)
    raise RuntimeError('Retry exhausted')
def sync(args):
    DATA.mkdir(exist_ok=True)
    state_path=DATA/'sync_state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    existing={r['paper_id']:r for r in read('papers.jsonl')}
    quarantine=read('quarantine.jsonl'); audit=read('audit.jsonl')
    stage=DATA/'staging'/('backfill' if args.backfill else 'incremental')
    stage.mkdir(parents=True,exist_ok=True)
    checkpoint=stage/'checkpoint.json'
    progress=json.loads(checkpoint.read_text()) if checkpoint.exists() else {'feed':0,'cursor':'*','started':now()}
    staged=stage/'records.jsonl'
    records=[json.loads(s) for s in staged.read_text().splitlines()] if staged.exists() else []
    feeds=[(issn,kind) for issn in ['1097-0266','0143-2095'] for kind in (['all'] if args.backfill else ['index','recent'])]
    contact=os.getenv('CROSSREF_MAILTO','')
    headers={'User-Agent':'SMJResearchAtlas/0.1'+(' (mailto:'+contact+')' if contact else '')}
    pages=0
    with httpx.Client(timeout=60,headers=headers) as client:
        while progress['feed']<len(feeds) and pages<args.max_pages:
            issn,kind=feeds[progress['feed']]
            filters=['type:journal-article','from-pub-date:1980-01-01','until-pub-date:'+datetime.now(timezone.utc).date().isoformat()]
            if kind=='index':
                last=datetime.fromisoformat(state.get('last_successful_sync',progress['started']))-timedelta(days=7)
                filters.append('from-index-date:'+last.date().isoformat())
            if kind=='recent': filters[1]='from-pub-date:'+(datetime.now(timezone.utc)-timedelta(days=90)).date().isoformat()
            message=request(client,f'https://api.crossref.org/journals/{issn}/works',{'filter':','.join(filters),'rows':args.rows,'cursor':progress['cursor']})
            items=message['items']
            records.extend(items)
            # Persist only bibliographic fields, excluding abstracts and reference text.
            allowed={'DOI','ISSN','container-title','title','author','published','published-print','published-online','volume','issue','page','article-number','type','URL','indexed','license','relation','update-to','reference-count'}
            records=[{k:v for k,v in r.items() if k in allowed} for r in records]
            write(staged,lines(records))
            nxt=message.get('next-cursor')
            if len(items)<args.rows or not nxt or nxt==progress['cursor']:
                progress['feed']+=1; progress['cursor']='*'
            else: progress['cursor']=nxt
            write(checkpoint,json.dumps(progress)); pages+=1; time.sleep(0.7)
    if progress['feed']<len(feeds):
        print(json.dumps({'status':'staged_incomplete','pages':pages,'records':len(records),'resume':'repeat same sync command'})); return
    for raw in records:
        try: new=normalize(raw)
        except (ValueError,KeyError,AssertionError) as exc:
            q={'doi':raw.get('DOI'),'reason':str(exc)}
            if q not in quarantine: quarantine.append(q)
            continue
        old=existing.get(new['paper_id']); merged=upsert(old,new)
        if old and old!=merged: audit.append({'paper_id':new['paper_id'],'at':now(),'before':old,'after':merged})
        existing[new['paper_id']]=merged
    rows=sorted(existing.values(),key=lambda p:p['paper_id'])
    for row in rows: Paper.model_validate(row)
    write(DATA/'papers.jsonl',lines(rows)); write(DATA/'quarantine.jsonl',lines(quarantine)); write(DATA/'audit.jsonl',lines(audit))
    state.update(last_successful_sync=progress['started'],last_completed_at=now(),coverage_status='coverage_not_audited',last_mode='backfill' if args.backfill else 'incremental')
    write(state_path,json.dumps(state,indent=2))
    checkpoint.unlink(); staged.unlink()
    print(json.dumps({'status':'success','papers':len(rows),'quarantine':len(quarantine)}))
def validate():
    papers=read('papers.jsonl'); variables=read('variables.jsonl'); ids=set()
    for p in papers:
        Paper.model_validate(p); assert p['paper_id'] not in ids; ids.add(p['paper_id'])
    receipts={r['paper_id']:r for r in read('content_receipts.jsonl')}
    variable_ids=set()
    for v in variables:
        Variable.model_validate(v); assert v['paper_id'] in ids
        if v['variable_id'] in variable_ids:raise ValueError('Duplicate variable_id')
        variable_ids.add(v['variable_id'])
        if v.get('evidence_grade'):
            OperationalVariable.model_validate(v)
            if v['validation_status']=='validated_automatic':
                receipt=receipts.get(v['paper_id'],{})
                if not v.get('alignment_verified') or not receipt.get('accessible') or receipt.get('source_hash')!=v['source_hash']:raise ValueError('Variable lacks aligned full-text receipt')
    taxonomy_path=DATA/'ontology.yaml'
    if taxonomy_path.exists():
        taxonomy=yaml.safe_load(taxonomy_path.read_text(encoding='utf-8'))
        validate_taxonomy(taxonomy,read('classifications.jsonl'),papers,variables)
    return papers,variables
def build():
    papers,variables=validate()
    state=json.loads((DATA/'sync_state.json').read_text()) if (DATA/'sync_state.json').exists() else {}
    ontology=yaml.safe_load((DATA/'ontology.yaml').read_text(encoding='utf-8'))
    manual=read('classifications.jsonl')
    enrichment=read('enrichment.jsonl');receipts=read('content_receipts.jsonl');runs=read('extraction_runs.jsonl')
    assignments=classify(papers,ontology,enrichment,manual)
    validate_taxonomy(ontology,assignments,papers,variables)
    papers=enrich_papers(papers,ontology,assignments)
    extra={e['paper_id']:e for e in enrichment};content={r['paper_id']:r for r in receipts}
    by_variable={}
    for v in variables:by_variable.setdefault(v['paper_id'],[]).append(v)
    for p in papers:
        p['title']=display_text(p['title'])
        p['enrichment']=extra.get(p['paper_id']);p['content_access']=content.get(p['paper_id'],{'accessible':False,'missing_reason':'not_yet_attempted'})
        p['variables']=by_variable.get(p['paper_id'],[]);p['is_retracted']=extra.get(p['paper_id'],{}).get('is_retracted');p['article_kind']=article_kind(p)
        p['unknown_details']={k:None for k in ['sample_period','data_source','empirical_method','reported_association']}
    emerging=emerging_topics(papers,ontology)
    for e in emerging:e.update(validation_status='provisional',inference_origin='deterministic_rule',evidence_grade='E0_metadata',kind='discovered_topic',requires_owner_action=False)
    queue=[{'task_id':hashlib.sha256(p['paper_id'].encode()).hexdigest()[:16],'paper_id':p['paper_id'],'task_type':'fulltext_review','missing_evidence':'合法全文與逐篇衡量證據','priority':'normal','status':'open','created_at':p['last_synced_at'],'assigned_to':None,'completed_at':None,'audit_log':[]} for p in papers]
    existing={r['task_id']:r for r in read('review_queue.jsonl')}
    queue=[existing.get(r['task_id'],r) for r in queue]
    write(DATA/'review_queue.jsonl',lines(queue))
    years=sorted({p['publication_year'] for p in papers})
    report={'papers':len(papers),'verified_variables':sum(v['verification_status'] in {'measurement_verified','human_reviewed'} for v in variables),'verified_papers':len({v['paper_id'] for v in variables if v['verification_status'] in {'measurement_verified','human_reviewed'}}),'years':years,'coverage_status':'coverage_not_audited','denominator':'目前收錄之去重 SMJ Crossref 書目；未與出版社逐期目錄核對','quarantine':len(read('quarantine.jsonl')),'review_tasks':sum(t['status']=='open' for t in queue),'last_successful_sync':state.get('last_successful_sync')}
    report.update(taxonomy_version=ontology['version'],is_official_smj_taxonomy=False,
        approved_classifications=sum(a['review_status']=='approved' for a in assignments),
        suggested_classifications=sum(a['review_status']=='suggested' for a in assignments),emerging_topic_candidates=len(emerging))
    publisher=json.loads((DATA/'publisher_check.json').read_text(encoding='utf-8')) if (DATA/'publisher_check.json').exists() else {'status':'not_attempted','expected_articles':None,'missing_estimate':None}
    report.update(coverage(papers,variables,assignments,receipts,enrichment,publisher))
    analysis=derive(papers,variables,ontology,receipts,enrichment)
    title_map={p['paper_id']:p['title'] for p in papers}
    for v in variables:v['paper_title']=title_map[v['paper_id']]
    graph=research_graph(papers,variables,assignments,runs)
    paths=[dict(paper_id=v['paper_id'],variable_id=v['variable_id'],construct_en=v['construct_en'],topic_ids=next(p['taxonomy_tags']['active']['research_topic'] for p in papers if p['paper_id']==v['paper_id']),source_url=v['source_url'],evidence_locator=v['evidence_locator'],evidence_grade=v.get('evidence_grade'),validation_status=v.get('validation_status'),binding_method='same-paper automatic topic context; not a theoretical equivalence claim') for v in variables]
    out=ROOT/'public'/'data'; out.mkdir(parents=True,exist_ok=True)
    manifest={'source_revision':os.getenv('GITHUB_SHA'),'workflow_run':os.getenv('GITHUB_RUN_ID'),'generated_at':report['generated_at']}
    write(out/'publication.json',json.dumps(manifest))
    # Search metadata only; full records are chunked into per-paper detail files.
    search_fields=['paper_id','doi','title','authors','publication_year','domain_codes','theory_tags','method_tags','verification_status','oa_url','metadata_provenance']
    search_fields+=['taxonomy_version','taxonomy_tags','legacy_domain_codes','legacy_theory_tags']
    for p in papers:
        p['evidence_grades']=sorted({a.get('evidence_grade','E0_metadata') for a in p['classifications']})
        p['variable_labels']=[v['variable_label_original'] for v in p['variables']]
        p['fulltext_accessible']=p['content_access'].get('accessible',False)
        p['citation_count']=(p.get('enrichment') or {}).get('citation_count')
    search_fields+=['evidence_grades','variable_labels','fulltext_accessible','article_kind','citation_count']
    write(out/'papers.json',json.dumps([{k:p.get(k) for k in search_fields} for p in papers],ensure_ascii=False))
    for p in papers: write(out/'papers'/ (hashlib.sha256(p['paper_id'].encode()).hexdigest()[:16]+'.json'),json.dumps(p,ensure_ascii=False))
    issue_counts={}
    for p in papers:
        k=f"{p['publication_year']}/{p.get('volume')}/{p.get('issue')}";issue_counts[k]=issue_counts.get(k,0)+1
    issues=[dict(year_volume_issue=k,indexed_articles=n,publisher_expected_articles=None,coverage_status='not_reconciled') for k,n in sorted(issue_counts.items())]
    for name,obj in [('coverage_report',report),('coverage_issues',issues),('analytics',analysis),('gap_candidates',gap_candidates(papers,ontology)),('measurement_paths',paths),('research_graph',graph),('pipeline_history',read('pipeline_history.jsonl')),('ontology',[n for n in ontology['nodes'] if n['level']=='domain']),('taxonomy',ontology),('classifications',assignments),('emerging_topics',emerging),('variables',variables)]:
        write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False)); write(DATA/'generated'/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2))
    classification_queue=[dict(task_id='review:'+a['assignment_id'],paper_id=a['paper_id'],term_id=a['term_id'],assignment_id=a['assignment_id'],taxonomy_version=a['taxonomy_version'],task_type='classification_review',status='open',origin=a['origin'],method=a['method'],source_url=a['source_url'],evidence_locator=a['evidence_locator']) for a in assignments if a['review_status']=='suggested']
    write(DATA/'generated'/'classification_review_queue.jsonl',lines(classification_queue))
    write(ROOT/'docs'/'COVERAGE_REPORT.md','# 涵蓋率報告\n\n'+json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))

def review_classification(args):
    required=[args.assignment_id,args.decision,args.reviewer,args.note,args.source_url,args.evidence_locator]
    if not args.human_attestation or not all(required):
        raise ValueError('Manual review requires --human-attestation, --assignment-id, --decision, --reviewer, --note, --source-url and --evidence-locator. Never run this in scheduled jobs.')
    build()
    proposals=json.loads((DATA/'generated'/'classifications.json').read_text(encoding='utf-8'))
    selected=next((a for a in proposals if a['assignment_id']==args.assignment_id),None)
    if selected is None and args.assignment_id.startswith('suggestion:'):
        # v2 IDs remain usable for optional historical decisions after the v3 migration.
        taxonomy=yaml.safe_load((DATA/'ontology.yaml').read_text(encoding='utf-8'))
        legacy=next((a for a in suggest_assignments(read('papers.jsonl'),taxonomy) if a['assignment_id']==args.assignment_id),None)
        if legacy:
            selected=next((a for a in proposals if a['paper_id']==legacy['paper_id'] and a['term_id']==legacy['term_id']),None)
            if selected:selected['assignment_id']=args.assignment_id
    if selected is None: raise ValueError('Unknown assignment_id in current taxonomy')
    previous=selected['review_status'];decision='approved' if args.decision=='approve' else 'rejected'
    stamp=now()
    selected.update(review_status=decision,reviewer=args.reviewer,reviewed_at=stamp,source_url=args.source_url,evidence_locator=args.evidence_locator)
    selected['audit_log'].append(dict(at=stamp,reviewer=args.reviewer,previous_status=previous,decision=decision,note=args.note,source_url=args.source_url,evidence_locator=args.evidence_locator,human_attestation=True))
    Assignment.model_validate(selected)
    manual={a['assignment_id']:a for a in read('classifications.jsonl')};manual[selected['assignment_id']]=selected
    write(DATA/'classifications.jsonl',lines(sorted(manual.values(),key=lambda a:a['assignment_id'])))
    build()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['sync','build','validate','review-classification']); parser.add_argument('--backfill',action='store_true'); parser.add_argument('--max-pages',type=int,default=20); parser.add_argument('--rows',type=int,default=500)
    parser.add_argument('--assignment-id');parser.add_argument('--decision',choices=['approve','reject']);parser.add_argument('--reviewer');parser.add_argument('--note');parser.add_argument('--source-url');parser.add_argument('--evidence-locator');parser.add_argument('--human-attestation',action='store_true');args=parser.parse_args()
    if args.command=='sync':
        try: sync(args)
        except Exception as exc:
            write(DATA/'staging'/'last_error.json',json.dumps({'at':now(),'error':str(exc)})); raise
    elif args.command=='build': build()
    elif args.command=='review-classification': review_classification(args)
    else: validate(); print('Data validation passed')
if __name__=='__main__': main()
