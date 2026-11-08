"""Evidence-limited audit of unclassified SMJ abstracts.

Fetches OpenAlex abstracts into volatile memory (never commits/re-publishes
copyrighted text); outputs only aggregate ngrams and tiny context cues.
Designed to reveal ontology omissions and indexing gaps, not assert theory use.

Usage: python -m pipeline.taxonomy_gap_audit --batches 12 --top 90
"""
import argparse
import collections
import hashlib
import json
import re
import time
from pathlib import Path

import httpx

from .cli import DATA,read
from .classify import classify
from .analytics import article_kind
from .enrich import abstract_text, FIELDS
from .taxonomy import text_key

STOP=set("""the of and to in for on from with by an a we our their this that are is was were as at
among across between using use used study studies examine examines examined examining research
find finds found results results suggest suggests show shows investigate investigating
firm firms organization organizations organizational companies company business businesses
strategy strategic management performance effect effects impact impacts relationship relationships
evidence paper article analysis level within under over through has have had can may more less
these those such however while research context approach approaches based role roles new
positive negative influence influences key how why when where which into its it they them
also one two three four both results data reveal suggests associated association link links
empirical theoretical explore explores question questions test tests first second different
""".split())

TARGET = {'theory': 'OTHER-TH', 'construct': 'OTHER-CON'}
GENERIC={"firm performance","company performance","business strategy","strategic management",
"research and development","our findings","the results","our analysis"}
THEORY_CUES=("theory","theories","perspective","perspectives","framework","frameworks",
             "logic","logics","view","views","paradigm","model")
CONSTRUCT_CUES=("innovation","learning","capability","capabilities","knowledge",
"competition","leadership","board","directors","governance","uncertainty",
"experience","diversity","risk","allocation","dependence","investment",
"identity","integration","search","rivalry","resource","resources",
"performance","political","embeddedness","orientation","acquisition",
"internationalization","mobility","reputation","institutional",
"network","scope","entrepreneurship","technology","capital","power",
"coordination","collaboration","resilience","trust","disclosure",
"responsibility","attention","dynamics","change","cognition","stakeholder")

def meaningful(phrase,known):
    if phrase in known or phrase in GENERIC:return False
    words=phrase.split()
    if any(len(w)<3 for w in words):return False
    if words[0] in STOP or words[-1] in STOP:return False
    if sum(w in STOP for w in words)>=max(1,len(words)-1):return False
    return True


def ngrams(abstract):
    tokens=text_key(abstract).split()
    out=set()
    for size in (2,3,4):
        for i in range(len(tokens)-size+1):
            phrase=' '.join(tokens[i:i+size])
            out.add(phrase)
    return out


def choose_papers(papers,enrichment,assignments,dimension,limit):
    bypaper=collections.defaultdict(set)
    for a in assignments:
        if a['review_status']!='rejected' and not a.get('is_fallback_other') and a.get('validation_status') in {'validated_automatic','provisional'}:
            bypaper[a['paper_id']].add(a['term_id'])
    nodes=json.loads((DATA/'ontology.yaml').read_text(encoding='utf-8'))['nodes']
    levels={n['id']:n['level'] for n in nodes}
    rows=[p for p in papers if
          article_kind(p)=='research_or_other_unresolved' and
          enrichment.get(p['paper_id'],{}).get('abstract_available') and
          enrichment.get(p['paper_id'],{}).get('openalex_id') and
          not any(levels.get(t)==dimension for t in bypaper[p['paper_id']])]
    # round-robin across decades, not just the newest or newest-first.
    bydecade=collections.defaultdict(list)
    for p in rows:
        bydecade[(p['publication_year']//10)*10].append(p)
    for decade in bydecade:
        bydecade[decade].sort(key=lambda p:hashlib.sha256((p['paper_id']+'|atlas-gap-v1').encode()).hexdigest())
    chosen=[]
    for index in range(limit):
        decades=[d for d in sorted(bydecade) if bydecade[d]]
        if not decades:break
        decade=decades[index%len(decades)]
        chosen.append(bydecade[decade].pop())
    return rows,chosen


def audit(batches=12,top=80,print_examples=2):
    from .cli import lines
    papers=read('papers.jsonl')
    enriched=read('enrichment.jsonl')
    enmap={e['paper_id']:e for e in enriched}
    taxonomy=json.loads((DATA/'ontology.yaml').read_text(encoding='utf-8'))
    assignments=classify(papers,taxonomy,enriched,read('classifications.jsonl'))
    selected={}
    candidates={}
    for dimension in TARGET:
        pool,chosen=choose_papers(papers,enmap,assignments,dimension,batches*20)
        selected[dimension]=dict(abstract_accessible_unresolved=len(pool),selected=len(chosen))
        candidates[dimension]={p['doi']:p for p in chosen}
    union={doi:p for group in candidates.values() for doi,p in group.items()}
    # Preserve independent dimension selection instead of accidentally
    # double-counting repeated paper in both samples.
    matched=collections.defaultdict(dict)
    failures=[]
    with httpx.Client(timeout=40,headers={'User-Agent':'SMJResearchAtlas/5.0 (abstract gap audit)'}) as client:
        dois=sorted(union)
        for offset in range(0,len(dois),40):
            chunk=dois[offset:offset+40]
            params={'filter':'doi:'+'|'.join('https://doi.org/'+doi for doi in chunk),
                    'per_page':100,
                    'select':'id,doi,abstract_inverted_index,publication_year,title'}
            try:
                response=client.get('https://api.openalex.org/works',params=params)
                response.raise_for_status()
                for raw in response.json().get('results',[]):
                    doi=(raw.get('doi') or '').lower().removeprefix('https://doi.org/')
                    if doi not in union:continue
                    abstract=abstract_text(raw.get('abstract_inverted_index'))
                    if not abstract:continue
                    matched[doi]['abstract']=abstract
                    matched[doi]['openalex_id']=raw.get('id')
            except (httpx.HTTPError,ValueError) as exc:
                failures.append(dict(offset=offset,error=type(exc).__name__,
                                     status=getattr(getattr(exc,'response',None),'status_code',None)))
            time.sleep(.25)
    known={text_key(x) for n in taxonomy['nodes'] for x in [n['label_en'],*n.get('match_phrases',[])] if text_key(x)}
    report={'taxonomy_version':taxonomy['version'],'sampling':'stratified decade round-robin, stable DOI hash',
            'methods':'whole OpenAlex abstract in-memory ngram exploratory counting; no author-theory inference',
            'dimensions':{},'batches_requested':batches,'requested_unique_dois':len(union),
            'fetched_full_abstracts_in_memory':sum(bool(x.get('abstract')) for x in matched.values()),
            'api_failures':failures}
    for dimension,group in candidates.items():
        counts=collections.Counter()
        examples=collections.defaultdict(list)
        audited=0
        for doi,p in group.items():
            text=matched.get(doi,{}).get('abstract')
            if not text:continue
            audited+=1
            phrases=ngrams(text)
            if dimension=='theory':
                phrases={s for s in phrases if any(re.search(r'\b'+re.escape(cue)+r'\b',s)
                          for cue in THEORY_CUES)}
            else:
                phrases={s for s in phrases if any(re.search(r'\b'+re.escape(cue)+r'\b',s)
                          for cue in CONSTRUCT_CUES)}
            for phrase in phrases:
                if not meaningful(phrase,known):continue
                counts[phrase]+=1
                if len(examples[phrase])<print_examples:
                    examples[phrase].append(dict(doi=doi,year=p['publication_year'],
                                          title=p['title'][:105]))
        terms=[dict(phrase=phrase,documents=count,examples=examples[phrase])
               for phrase,count in counts.most_common() if count>=2][:top]
        report['dimensions'][dimension]=dict(**selected[dimension],audited_abstracts=audited,
                                               candidate_phrases=terms)
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--batches',type=int,default=12)
    parser.add_argument('--top',type=int,default=80)
    args=parser.parse_args()
    audit(batches=args.batches,top=args.top)


if __name__=='__main__':main()
