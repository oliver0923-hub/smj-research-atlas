"""Validated data artifacts, reproducible releases, and source-access health."""
import argparse,gzip,hashlib,json,subprocess,time,os,io,zipfile
from pathlib import Path
import httpx
from .cli import ROOT,DATA,read,write,lines,build,validate,sync
from .core import Paper,now
from .evidence import OperationalVariable
from .study import StudyClaim

TABLES=['papers.jsonl','variables.jsonl','study_claims.jsonl','enrichment.jsonl','content_receipts.jsonl','extraction_runs.jsonl','pipeline_history.jsonl','audit.jsonl','quarantine.jsonl','crawl_queue.jsonl','crawl_control.jsonl','research_records.jsonl','research_quarantine.jsonl','crawl_events.jsonl']

def snapshot():
    validate()
    checkpoints={name:json.loads((DATA/'staging'/name).read_text()) for name in ['openalex_checkpoint.json'] if (DATA/'staging'/name).exists()}
    payload={'schema_version':'4.0.0','tables':{name:read(name) for name in TABLES},'checkpoints':checkpoints,'state':json.loads((DATA/'sync_state.json').read_text()),'publisher_check':json.loads((DATA/'publisher_check.json').read_text()) if (DATA/'publisher_check.json').exists() else {}}
    blob=gzip.compress(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode(),mtime=0)
    target=DATA/'live_state.json.gz';tmp=target.with_suffix('.tmp');tmp.write_bytes(blob);tmp.replace(target)
    return {'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}

def restore(ref=None):
    if ref:
        result=subprocess.run(['git','show',ref+':data/live_state.json.gz'],capture_output=True)
        if result.returncode:return {'status':'no_previous_data_branch'}
        blob=result.stdout
    else:
        path=DATA/'live_state.json.gz'
        if not path.exists():return {'status':'bootstrap'}
        blob=path.read_bytes()
    payload=json.loads(gzip.decompress(blob));tables=payload['tables']
    if payload.get('schema_version') in {'3.0.0','3.1.0'}:
        for name in TABLES:tables.setdefault(name,[])
    elif payload.get('schema_version')!='4.0.0':raise ValueError('Unrecognized data artifact')
    if set(tables)!=set(TABLES):raise ValueError('Unrecognized data artifact')
    from .research import validate_record
    for record in tables['research_records.jsonl']:validate_record(record)
    papers=tables['papers.jsonl'];ids=set()
    for p in papers:Paper.model_validate(p);assert p['paper_id'] not in ids;ids.add(p['paper_id'])
    for v in tables['variables.jsonl']:
        if v.get('evidence_grade'):OperationalVariable.model_validate(v)
        assert v['paper_id'] in ids
    for claim in tables['study_claims.jsonl']:
        StudyClaim.model_validate(claim)
        assert claim['paper_id'] in ids
    # Current actual human edits take precedence over automatic data artifacts.
    human={v['variable_id']:v for v in read('variables.jsonl') if v.get('human_reviewer')}
    values={v['variable_id']:v for v in tables['variables.jsonl']};values.update(human);tables['variables.jsonl']=list(values.values())
    for name,rows in tables.items():write(DATA/name,lines(rows))
    write(DATA/'sync_state.json',json.dumps(payload['state'],indent=2))
    write(DATA/'publisher_check.json',json.dumps(payload.get('publisher_check',{}),indent=2))
    for name,value in payload.get('checkpoints',{}).items():
        if name=='openalex_checkpoint.json':write(DATA/'staging'/name,json.dumps(value))
    return {'status':'restored','papers':len(papers)}

def restore_checkpoints():
    token=os.getenv('GITHUB_TOKEN');repo='oliver0923-hub/smj-research-atlas'
    if not token:return {'status':'disabled_outside_github','restored':0}
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'}
    allowed={'incremental/checkpoint.json','incremental/records.jsonl','openalex_checkpoint.json'}
    with httpx.Client(timeout=40,follow_redirects=True,headers=headers) as client:
        runs=client.get(f'https://api.github.com/repos/{repo}/actions/workflows/sync-metadata.yml/runs',params={'branch':'main','status':'completed','per_page':5});runs.raise_for_status()
        for run in runs.json()['workflow_runs']:
            arts=client.get(f'https://api.github.com/repos/{repo}/actions/runs/{run["id"]}/artifacts');arts.raise_for_status()
            artifact=next((a for a in arts.json()['artifacts'] if a['name']=='pipeline-diagnostics' and not a['expired']),None)
            if not artifact:continue
            response=client.get(artifact['archive_download_url']);response.raise_for_status();count=0
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                for info in archive.infolist():
                    name=info.filename.removeprefix('staging/')
                    if name not in allowed or info.file_size>20_000_000:continue
                    text=archive.read(info).decode('utf-8')
                    if name.endswith('checkpoint.json'):json.loads(text)
                    else:
                        for line in text.splitlines():json.loads(line)
                    write(DATA/'staging'/name,text);count+=1
            return {'status':'restored','files':count,'source_run':run['id']}
    return {'status':'no_checkpoint_artifact','files':0}

def publisher_check():
    url='https://sms.onlinelibrary.wiley.com/loi/10970266'
    report=dict(source_url=url,checked_at=now(),all_issues_audited=False,expected_articles=None,missing_estimate=None,status='unavailable')
    try:
        r=httpx.get(url,timeout=25,follow_redirects=True,headers={'User-Agent':'SMJResearchAtlas/3.0'})
        report.update(http_status=r.status_code,status='accessible_partial_not_reconciled' if r.is_success else 'publisher_access_blocked',response_sha256=hashlib.sha256(r.content).hexdigest())
    except httpx.HTTPError as exc:report['error_type']=type(exc).__name__
    write(DATA/'publisher_check.json',json.dumps(report,indent=2));return report

def gate():
    papers,variables=validate()
    baseline=json.loads((DATA/'migrations/v3_baseline.json').read_text(encoding='utf-8'))
    if len(papers)<baseline['unique_doi']:raise ValueError('Published corpus shrank without a verified tombstone migration')
    if len({p['doi'] for p in papers})!=len(papers):raise ValueError('Duplicate DOI')
    for v in variables:
        if v.get('human_reviewer') and v.get('inference_origin') not in {None,'human_review'}:raise ValueError('Automatic extraction cannot fabricate a reviewer')
    return {'status':'passed','papers':len(papers),'variables':len(variables),'validation_scope':'schema, provenance, referential consistency; not peer review'}

def refresh(mode='daily',dry_run=False):
    from argparse import Namespace
    from .enrich import harvest
    from .crawl import tick
    if mode in {'exhaust_oa','continue_oa','pause_oa','resume_oa','restart_oa'}:
        from .crawl import tick
        if dry_run:return {'status':'dry_run','mode':mode,'source_budget':180,'requests':450,'seconds':600,'paid_api_calls':0}
        result=tick(mode,persist=os.getenv('GITHUB_ACTIONS')=='true')
        snapshot();build();return result
    if dry_run:return {'status':'dry_run','mode':mode,'metadata_pages':20,
        'enrichment_requests':12 if mode in {'weekly','batch'} else 4 if mode=='daily' else 0,
        'fulltext_papers':60 if mode=='batch' else 40 if mode=='weekly' else 4 if mode=='daily' else 0,
        'paid_api_calls':0,'publication_gate':'schema+tests+build'}
    start=time.perf_counter();run={'started_at':now(),'mode':mode,'status':'running'}
    try:
        if mode in {'daily','weekly','batch'}:
            sync(Namespace(backfill=False,max_pages=20,rows=500))
            if (DATA/'staging/incremental/checkpoint.json').exists():raise ValueError('Incremental sync incomplete; old deployment retained')
        if mode=='daily':
            # Upgrade all previously indexed abstract features in bounded
            # blocks instead of letting a six-thousand-tag ontology refresh
            # trickle in at four API calls each day. No extra fulltext requests.
            backlog=sum(e.get('abstract_feature_method')!='allowed_phrase_occurrence_v6'
                        for e in read('enrichment.jsonl'))
            pages=20 if backlog>=160 else 4
            run['taxonomy_backfill_backlog_at_start']=backlog
            run['enrichment']=harvest(pages,priority_new=True)
            run['acquisition']=tick('continue_oa',max_sources=4,max_requests=20,seconds=150,persist=os.getenv('GITHUB_ACTIONS')=='true')
        if mode in {'weekly','batch'}:
            run['enrichment']=harvest(12)
            run['new_papers_enrichment']=harvest(4,priority_new=True)
            # Manual batch jobs share the same strict budget and validation
            # gate as scheduled jobs; 720 seconds leaves time for build/deploy.
            count=60 if mode=='batch' else 40
            seconds=720 if mode=='batch' else 600
            run['acquisition']=tick('continue_oa',max_sources=count,max_requests=count*3,seconds=seconds,persist=os.getenv('GITHUB_ACTIONS')=='true')
        run['publisher']=publisher_check();run['quality']=gate();run['status']='validated_automatic'
    except Exception as exc:
        run.update(status='failed',error_type=type(exc).__name__);raise
    finally:
        run.update(finished_at=now(),runtime_seconds=round(time.perf_counter()-start,3))
        write(DATA/'pipeline_history.jsonl',lines((read('pipeline_history.jsonl')+[run])[-100:]))
    build();snapshot();return run

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['snapshot','restore','refresh','gate','publisher','restore-checkpoints']);p.add_argument('--from-ref');p.add_argument('--mode',choices=['daily','weekly','batch','monthly','exhaust_oa','continue_oa','pause_oa','resume_oa','restart_oa'],default='daily');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    action={'snapshot':snapshot,'restore':lambda:restore(a.from_ref),'restore-checkpoints':restore_checkpoints,'refresh':lambda:refresh(a.mode,a.dry_run),'gate':gate,'publisher':publisher_check}[a.command]
    print(json.dumps(action(),ensure_ascii=False))
if __name__=='__main__':main()
