"""Run with python -m pipeline.cli sync|build|validate."""
import argparse, json, os, random, time, hashlib, gzip
from pathlib import Path
from datetime import datetime, timedelta, timezone
import httpx, yaml
from .core import normalize, upsert, now, Paper, Variable
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
            allowed={'DOI','ISSN','container-title','title','author','published','published-print','published-online','volume','issue','page','article-number','type','URL','indexed'}
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
    for v in variables: Variable.model_validate(v); assert v['paper_id'] in ids
    return papers,variables
def build():
    papers,variables=validate()
    state=json.loads((DATA/'sync_state.json').read_text()) if (DATA/'sync_state.json').exists() else {}
    ontology=yaml.safe_load((DATA/'ontology.yaml').read_text(encoding='utf-8'))
    queue=[{'task_id':hashlib.sha256(p['paper_id'].encode()).hexdigest()[:16],'paper_id':p['paper_id'],'task_type':'fulltext_review','missing_evidence':'合法全文與逐篇衡量證據','priority':'normal','status':'open','created_at':p['last_synced_at'],'assigned_to':None,'completed_at':None,'audit_log':[]} for p in papers]
    existing={r['task_id']:r for r in read('review_queue.jsonl')}
    queue=[existing.get(r['task_id'],r) for r in queue]
    write(DATA/'review_queue.jsonl',lines(queue))
    years=sorted({p['publication_year'] for p in papers})
    report={'papers':len(papers),'verified_variables':sum(v['verification_status'] in {'measurement_verified','human_reviewed'} for v in variables),'verified_papers':len({v['paper_id'] for v in variables if v['verification_status'] in {'measurement_verified','human_reviewed'}}),'years':years,'coverage_status':'coverage_not_audited','denominator':'目前收錄之去重 SMJ Crossref 書目；未與出版社逐期目錄核對','quarantine':len(read('quarantine.jsonl')),'review_tasks':sum(t['status']=='open' for t in queue),'last_successful_sync':state.get('last_successful_sync')}
    out=ROOT/'public'/'data'; out.mkdir(parents=True,exist_ok=True)
    # Search metadata only; full records are chunked into per-paper detail files.
    search_fields=['paper_id','doi','title','authors','publication_year','domain_codes','theory_tags','method_tags','verification_status','oa_url','metadata_provenance']
    write(out/'papers.json',json.dumps([{k:p.get(k) for k in search_fields} for p in papers],ensure_ascii=False))
    for p in papers: write(out/'papers'/ (hashlib.sha256(p['paper_id'].encode()).hexdigest()[:16]+'.json'),json.dumps(p,ensure_ascii=False))
    for name,obj in [('coverage_report',report),('ontology',ontology),('variables',variables)]:
        write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False)); write(DATA/'generated'/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2))
    write(ROOT/'docs'/'COVERAGE_REPORT.md','# 涵蓋率報告\n\n'+json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['sync','build','validate']); parser.add_argument('--backfill',action='store_true'); parser.add_argument('--max-pages',type=int,default=20); parser.add_argument('--rows',type=int,default=500); args=parser.parse_args()
    if args.command=='sync':
        try: sync(args)
        except Exception as exc:
            write(DATA/'staging'/'last_error.json',json.dumps({'at':now(),'error':str(exc)})); raise
    elif args.command=='build': build()
    else: validate(); print('Data validation passed')
if __name__=='__main__': main()
