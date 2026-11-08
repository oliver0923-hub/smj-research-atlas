"""Held-out source-annotated reviewed subset; never manufacture labels from outputs."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from .article import parse_article
from .research import extraction,key

ROOT=Path(__file__).resolve().parents[1]


def canonical(value,field):
    value=re.sub(r'[^a-z0-9]+',' ',str(value).lower()).strip()
    if field=='sample_period':
        years=re.findall(r'(?:19|20)\d{2}',value)
        return '–'.join(years[:2]) if len(years)>=2 else value
    aliases={'ordinary least squares':'ols','logistic regression':'logit',
        'cox proportional hazard':'cox','cox proportional hazards':'cox','hazard model':'cox',
        'difference in differences':'did','randomized controlled trial':'rct',
        'fuzzy set qualitative comparative analysis':'qca','qualitative comparative analysis':'qca',
        'thomson reuters':'thomson_reuters','sdc platinum':'sdc'}
    return aliases.get(value,value.replace(' ','_'))


def metrics(tp,fp,fn):
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    return dict(tp=tp,fp=fp,fn=fn,precision=precision,recall=recall,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)


def scoped_values(field,values,ids,evidence,blocks,pages):
    spans=[blocks[evidence[i]['block_id']]['text'][evidence[i]['start']:evidence[i]['end']]
           for i in ids if evidence[i]['page'] in pages]
    if field=='sample_period':
        return [v for v in values if any(all(y in span for y in re.findall(r'(?:19|20)\d{2}',str(v))) for span in spans)]
    return [v for v in values if any(key(str(v)) in key(span) for span in spans)]


def evaluate(manifest):
    gold=json.loads((ROOT/'evaluation/gold.json').read_text(encoding='utf-8'))
    frozen=json.loads((ROOT/'evaluation/frozen_extractor.json').read_text())
    for path,expected in frozen.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Frozen extractor changed; do not tune using evaluation labels: '+path)
    raw={p['paper_id']:p for p in json.loads(Path(manifest).read_text())}
    from .cli import read
    metadata={p['paper_id']:p for p in read('papers.jsonl')}
    totals={};details=[]
    for p in gold['papers']:
        private=raw[p['paper_id']];content=(ROOT/private['private_raw']).read_bytes()
        if hashlib.sha256(content).hexdigest()!=p['source_hash']:raise ValueError('Evaluation source changed')
        cached=ROOT/'.cache/articles'/(hashlib.sha256(p['paper_id'].encode()).hexdigest()[:16]+'-'+p['source_hash'][:12]+'.json')
        if cached.exists():
            from .article import ArticleDocument
            doc=ArticleDocument(**json.loads(cached.read_text(encoding='utf-8')))
            if doc.source_hash!=p['source_hash']:raise ValueError('Cached source mismatch')
        else:doc=parse_article(metadata[p['paper_id']],content,p['content_type'],dict(source_url=p['source_url'],source_hash=p['source_hash']))
        result=extraction(doc);ev={e['evidence_id']:e for e in result['evidence']}
        blocks={b['block_id']:b for b in doc.blocks}
        for field,expected in p['queries'].items():
            f=result['fields'][field]
            # Restrict predictions to independently reviewed pages, including negative cases.
            values=f['value'] if isinstance(f['value'],list) else [f['value']] if f['value'] is not None else []
            if field=='sample_period' and len(values)==2 and all(isinstance(v,int) for v in values):
                values=[str(values[0])+'–'+str(values[1])]
            values=scoped_values(field,values,f['evidence_ids'],ev,blocks,p['reviewed_pages'])
            predicted={canonical(v,field) for v in values}
            wanted={canonical(v,field) for v in expected}
            tp=len(predicted&wanted);fp=len(predicted-wanted);fn=len(wanted-predicted)
            t=totals.setdefault(field,dict(tp=0,fp=0,fn=0,queries=0,exact_matches=0,abstentions=0))
            for k,v in [('tp',tp),('fp',fp),('fn',fn)]:t[k]+=v
            t['queries']+=1;t['exact_matches']+=predicted==wanted;t['abstentions']+=not predicted and bool(wanted)
            details.append(dict(doi=p['doi'],field=field,expected=sorted(wanted),predicted=sorted(predicted),
                exact_match=predicted==wanted,unknown_reason=f.get('reason') if not predicted else None,pages=p['reviewed_pages']))
    fields={k:dict(**metrics(v['tp'],v['fp'],v['fn']),queries=v['queries'],exact_matches=v['exact_matches'],
        exact_match_rate=v['exact_matches']/v['queries'],abstentions=v['abstentions']) for k,v in totals.items()}
    micro=metrics(*(sum(v[k] for v in totals.values()) for k in ['tp','fp','fn']))
    output=dict(schema_version='1.0',status='independent_source_reviewed_subset',papers=len(gold['papers']),
        queries=len(details),sampling=gold['sampling'],scope=gold['scope'],extractor_hashes=frozen,
        gold_sha256=hashlib.sha256((ROOT/'evaluation/gold.json').read_bytes()).hexdigest(),
        human_review_status='No second blind expert review; source alignment is not semantic accuracy',
        fields=fields,micro=micro,other_fields_accuracy=None,details=details)
    (ROOT/'evaluation/results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='details'},ensure_ascii=True))
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',default='.cache/evaluation_manifest.json')
    evaluate(p.parse_args().manifest)
