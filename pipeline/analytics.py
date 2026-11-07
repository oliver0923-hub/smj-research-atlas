"""Denominator-aware derived datasets. No inferred causal findings or research gaps."""
import hashlib
import json
import re
from collections import Counter,defaultdict
from itertools import combinations
from .core import now

def article_kind(paper):
    if paper.get('is_retracted') is True:return 'retracted'
    title=re.sub(r'<[^>]+>','',paper['title']).strip().lower()
    if re.match(r'^(correction|corrigendum|erratum|retraction|editorial|book reviews?|author index|subject index|contents|announcements?|editorial board|masthead|cover image|front matter|back matter|review of the book)\b',title):return 'editorial_or_notice'
    return 'research_or_other_unresolved'

def derive(papers,variables,taxonomy,receipts=(),enrichment=()):
    available={r['paper_id'] for r in receipts if r.get('accessible')}
    node_map={n['id']:n for n in taxonomy['nodes']};years=sorted({p['publication_year'] for p in papers})
    in_scope=[p for p in papers if article_kind(p) not in {'editorial_or_notice','retracted'}]
    year_counts=Counter(p['publication_year'] for p in in_scope)
    topic_counts=Counter();pairs=Counter();matrix=Counter();year_topic=Counter();representatives=defaultdict(list)
    citation={e['paper_id']:e.get('citation_count') or 0 for e in enrichment}
    for p in in_scope:
        tags=p['taxonomy_tags']['active'];topics=set(tags['research_topic']);theories=set(tags['theory'])
        topic_counts.update(topics);pairs.update(combinations(sorted(topics),2));matrix.update((t,topic) for t in theories for topic in topics)
        year_topic.update((p['publication_year'],topic) for topic in topics)
        for topic in topics:representatives[topic].append({'paper_id':p['paper_id'],'title':p['title'],'year':p['publication_year'],'citations':citation.get(p['paper_id'],0),'fulltext_accessible':p['paper_id'] in available})
    for topic,rows in representatives.items():rows.sort(key=lambda p:(-p['citations'],-p['year'],p['paper_id']))
    supported=[v for v in variables if v.get('evidence_grade')=='E3_measurement_text' and v.get('validation_status')=='validated_automatic']
    measure_papers={v['paper_id'] for v in supported}
    roles=Counter(v.get('role','unknown') for v in supported)
    methods=Counter(v['empirical_method'] for v in supported if v.get('empirical_method'))
    datasets=Counter(v['data_source'] for v in supported if v.get('data_source'))
    return dict(paper_facts=[dict(paper_id=p['paper_id'],year=p['publication_year'],title=p['title'],kind=article_kind(p),fulltext=p['paper_id'] in available,tags=[dict(term_id=a['term_id'],grade=a.get('evidence_grade','E0_metadata'),status=a.get('validation_status','provisional'),score=a.get('heuristic_score')) for a in p['classifications'] if a['review_status']!='rejected']) for p in papers],version='3.0.0',generated_at=now(),scope='目前收錄且未由標題明確識別為社論／更正的書目；未全部驗證研究文章類型',
        denominator=len(in_scope),excluded_notices=len(papers)-len(in_scope),multilabel=True,
        yearly=[{'year':y,'papers':year_counts[y],'incomplete_recent_year':y==max(years),'topics':[dict(topic_id=t,count=year_topic[(y,t)],share=year_topic[(y,t)]/year_counts[y] if year_counts[y] else None) for t in sorted(topic_counts)]} for y in years],
        topic_counts=[{'topic_id':t,'label':node_map[t]['label_zh'],'count':n,'share':n/len(in_scope) if in_scope else None} for t,n in topic_counts.most_common()],
        cooccurrence=[{'a':a,'b':b,'papers':n} for (a,b),n in pairs.most_common(60)],
        theory_topic=[{'theory_id':t,'topic_id':topic,'papers':n} for (t,topic),n in sorted(matrix.items())],
        representatives={k:v[:10] for k,v in representatives.items()},
        measure_denominator_papers=len(measure_papers),measure_denominator_variables=len(supported),roles=dict(roles),methods=dict(methods),datasets=dict(datasets),
        opportunities=[{'a':a,'b':b,'joint_papers':n,'denominator':len(in_scope),'status':'descriptive_combination_only','rule':'各主題均至少10篇，且合併出現至多2篇；非新穎性或研究缺口證明'} for (a,b),n in sorted(pairs.items()) if n<=2 and topic_counts[a]>=10 and topic_counts[b]>=10][:15],
        limits=['自動分類的來源一致性檢查不等於專家審閱。','多重標記比例不可相加為100%。','未驗證的研究文章類型及近期未完整年度限制趨勢解讀。','方法／資料庫只統計 E3 紀錄內具文字證據者；未知不是零。'])

def coverage(papers,variables,assignments,receipts,enrichment,publisher):
    doi=[p['doi'] for p in papers];counts=Counter(p['publication_year'] for p in papers)
    classified={a['paper_id'] for a in assignments if a['review_status']!='rejected' and (a.get('validation_status') in {'validated_automatic','provisional'} or a['review_status']=='approved')}
    aligned=[v for v in variables if v.get('evidence_grade')=='E3_measurement_text' and v.get('validation_status')=='validated_automatic']
    return dict(papers=len(papers),unique_doi=len(set(doi)),duplicate_doi=len(doi)-len(set(doi)),duplicate_rate=(len(doi)-len(set(doi)))/len(doi) if doi else 0,
        missing_fields={field:sum(not p.get(field) for p in papers) for field in ['title','authors','volume','issue','pages','online_date','print_date']},
        years=sorted(counts),year_counts=dict(sorted(counts.items())),publication_type_mix=dict(Counter(article_kind(p) for p in papers)),
        classified_papers=len(classified),classification_denominator=len(papers),classification_coverage=len(classified)/len(papers) if papers else None,
        abstracts_available=sum(e.get('abstract_available',False) for e in enrichment),enriched_papers=len(enrichment),
        fulltexts_attempted=len(receipts),accessible_fulltexts=sum(r.get('accessible',False) for r in receipts),
        variable_records=len(variables),measurement_text_aligned=len(aligned),formula_backed_variables=sum(bool(v.get('formula')) for v in aligned),
        verified_variables=len(aligned),verified_papers=len({v['paper_id'] for v in aligned}),
        measure_coverage=len({v['paper_id'] for v in aligned})/len(papers) if papers else None,
        evidence_tiers=dict(Counter(a.get('evidence_grade','E0_metadata') for a in assignments)),validation_statuses=dict(Counter(a.get('validation_status','provisional') for a in assignments)),
        publisher_reconciliation=publisher,coverage_status='coverage_not_audited',missing_publisher_coverage_estimate=None,
        denominator='目前收錄之去重 SMJ Crossref 書目；出版社逐期完整母體未核對，缺漏比例未知',generated_at=now(),schema_version='3.0.0')

def research_graph(papers,variables,assignments,runs):
    constructs={};aliases=[];evidence=[]
    for v in variables:
        key='construct:'+hashlib.sha256(v['construct_en'].lower().encode()).hexdigest()[:16]
        constructs[key]={'construct_id':key,'label_en':v['construct_en'],'label_zh':v.get('construct_zh'),'origin':'fulltext_extraction'}
        v['construct_id']=key
        aliases.append({'alias_id':v['variable_id']+':alias','variable_id':v['variable_id'],'label':v['variable_label_original']})
        evidence.append({k:v.get(k) for k in ['variable_id','paper_id','source_url','evidence_locator','source_hash','span_hash','evidence_grade','validation_status','evidence_excerpt']})
    return dict(schema_version='3.0.0',paper=[{'paper_id':p['paper_id'],'doi':p['doi']} for p in papers],claim=assignments,
        theory_tag=[a for a in assignments if a['term_id'].startswith('TH-')],topic_tag=[a for a in assignments if a['term_id'].startswith('TOP-')],
        construct=list(constructs.values()),operational_variable=variables,variable_alias=aliases,measure_evidence=evidence,
        empirical_method=[],data_source=[],sample=[],finding=[],citation_provenance=[{'paper_id':p['paper_id'],'sources':p['metadata_provenance']} for p in papers],extraction_run=runs)


def gap_candidates(papers,taxonomy,minimum=10,maximum_joint=2):
    """Descriptive candidates with reproducible paper sets, never verified novelty."""
    nodes={n['id']:n for n in taxonomy['nodes']}
    scope=[p for p in papers if article_kind(p) not in {'editorial_or_notice','retracted'}]
    topics=defaultdict(set);theories=defaultdict(set)
    for p in scope:
        tags=p['taxonomy_tags']['active']
        for term in set(tags['research_topic']):topics[term].add(p['paper_id'])
        for term in set(tags['theory']):theories[term].add(p['paper_id'])
    eligible=sorted(t for t,ids in topics.items() if len(ids)>=minimum)
    rows=[]
    for a,b in combinations(eligible,2):
        joint=topics[a]&topics[b]
        if len(joint)>maximum_joint:continue
        rows.append(dict(candidate_id='gap:'+hashlib.sha256((a+'|'+b).encode()).hexdigest()[:16],
            topic_a=a,topic_b=b,label_a=nodes[a]['label_zh'],label_b=nodes[b]['label_zh'],
            papers_a=len(topics[a]),papers_b=len(topics[b]),joint_papers=len(joint),denominator=len(scope),
            support_paper_ids_a=sorted(topics[a])[:5],support_paper_ids_b=sorted(topics[b])[:5],joint_paper_ids=sorted(joint),
            associated_theories=[dict(theory_id=t,label=nodes[t]['label_zh'],papers=len(ids&(topics[a]|topics[b]))) for t,ids in sorted(theories.items()) if ids&(topics[a]|topics[b])],
            inference_origin='deterministic_rule',evidence_grade='E0_E1_classification_aggregate',validation_status='provisional',
            taxonomy_version=taxonomy['version'],algorithm_version='descriptive-gap-1.0',
            rule=dict(minimum_each_topic=minimum,maximum_joint=maximum_joint,exclude_notices_and_retracted=True),
            verified_research_gap=None,novelty=None,causal_interpretation=None))
    return dict(schema_version='3.0.0',generated_at=now(),automatic=True,scope='目前索引之自動分類；研究文章類型與全期刊母體尚未完全核實',denominator=len(scope),candidates=rows,
        limitations=['低共現可能來自分類漏判或來源覆蓋，不構成新穎性證明。','支撐文獻顯示主題標記，不表示作者提出相同研究缺口。','未知的理論機制、可行性與因果解釋保持 null。'])
