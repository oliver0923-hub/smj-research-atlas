"""Supplemental raw-source reviewed relationship subset, including abstentions."""
import hashlib
import json
from collections import Counter
from .article import ArticleDocument,digest
from .evaluate import ROOT,metrics
from .research import extraction,key


def run():
    gold=json.loads((ROOT/'evaluation/relationship_gold.json').read_text(encoding='utf-8'))
    frozen=json.loads((ROOT/'evaluation/frozen_extractor.json').read_text())
    for path,value in frozen.items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==value
    manifest={p['doi']:p for p in json.loads((ROOT/'.cache/evaluation_manifest.json').read_text())}
    records={}
    for source in gold['sources']:
        raw=(ROOT/manifest[source['doi']]['private_raw']).read_bytes()
        assert digest(raw)==source['source_hash']
        path=ROOT/'.cache/articles'/(digest(source['paper_id'])[:16]+'-'+source['source_hash'][:12]+'.json')
        doc=ArticleDocument(**json.loads(path.read_text(encoding='utf-8')))
        records[source['doi']]=extraction(doc)
    details=[];totals={}
    for q in gold['queries']:
        r=records[q['doi']];evidence={e['evidence_id']:e for e in r['evidence']}
        def located(row):return any(evidence[i]['page'] in q['pages'] for i in row['evidence_ids'])
        predicted=[];kind=q['kind']
        if kind.startswith('hypothesis_') and kind!='hypothesis_variable_model_link':
            field='reported_support' if kind=='hypothesis_support' else 'significance'
            predicted=[f[field] for f in r['findings'] if f['hypothesis_label'].lower()==q['label'].lower() and located(f) and f[field]!='unknown']
        elif kind=='variable_role':
            predicted=[v['fields']['role']['value'] for v in r['variables'] if key(v['name'])==key(q['variable']) and v['fields']['role']['value'] is not None and located(v['fields']['role'])]
        elif kind=='robustness_result':
            predicted=[c['result'] for c in r['checks'] if c['kind']=='robustness' and located(c) and c['result']!='unknown']
        elif kind=='hypothesis_variable_model_link':
            # Require all actual structured links; prose co-occurrence alone is insufficient.
            for f in r['findings']:
                if f['hypothesis_label'].lower()!=q['label'].lower() or not f['model_id']:continue
                model=next(m for m in r['models'] if m['model_id']==f['model_id'])
                names={key(v['name']) for v in r['variables'] if v['variable_id'] in f['variable_ids']}
                if model['table']==q['table'] and model['label'].strip('()')==q['model'] and {key(q['iv']),key(q['dv'])}<=names:predicted.append(True)
        else:
            field='reported_estimate' if kind=='model_estimate' else 'p_value'
            for estimate in r['estimates']:
                model=next(m for m in r['models'] if m['model_id']==estimate['model_id'])
                if model['table']==q['table'] and model['label'].strip('()')==q['model'] and key(estimate['variable_label'])==key(q['variable']) and located(estimate) and estimate.get(field) is not None:predicted.append(estimate[field])
        predicted=set(predicted);expected={q['expected']}
        tp=len(predicted&expected);fp=len(predicted-expected);fn=len(expected-predicted)
        t=totals.setdefault(kind,Counter());t.update(tp=tp,fp=fp,fn=fn,queries=1,abstentions=int(not predicted))
        details.append(dict(q,predicted=list(predicted),exact_match=predicted==expected))
    result=dict(method=gold['method'],papers=len(records),queries=len(details),extractor_hashes=frozen,
        fields={k:dict(**metrics(v['tp'],v['fp'],v['fn']),queries=v['queries'],abstentions=v['abstentions']) for k,v in totals.items()},details=details)
    (ROOT/'evaluation/relationship_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=True))
    return result


if __name__=='__main__':run()
