"""Regressions motivated by the 2026-11-08 unresolved SMJ abstract audit.

Examples are identified by real SMJ DOIs; phrase recognition is a *unit test*
of lexical evidence, not independently verified author theory adoption.
"""
import json
from pathlib import Path
from pipeline.classify import classify
from pipeline.taxonomy import validate_taxonomy,enrich_papers
from pipeline.analytics import coverage
from pipeline.taxonomy_gap_audit import choose_papers,ngrams,meaningful

ROOT=Path(__file__).resolve().parents[1]
TAX=json.loads((ROOT/'data/ontology.yaml').read_text(encoding='utf-8'))


def article(doi,title,year=2015):
    return dict(paper_id='doi:'+doi,doi=doi,title=title,publication_year=year,
       last_synced_at='2026-11-08',
       metadata_provenance=[{'source_url':'https://api.crossref.org/works/'+doi}])


def test_ontology_v24_adds_source_audited_concepts_without_erasing_v23():
    nodes=validate_taxonomy(TAX)
    assert TAX['version']=='2.4.0'
    assert len([n for n in nodes.values() if n.level=='construct'])==116
    assert len([n for n in nodes.values() if n.level=='theory'])==50
    prior=json.loads((ROOT/'data/taxonomy_versions/2.3.0.json').read_text(encoding='utf-8'))
    assert prior['version']=='2.3.0'
    assert {n['id'] for n in prior['nodes']} <= set(nodes)
    assert len([n for n in nodes.values() if n.level=='domain'
                 and n.origin=='official_academic_organization'])==12


def test_real_surveyed_article_titles_cover_missing_constructs():
    titles=[
      ('10.1002/smj.4250171108','Strategic alliances and interfirm knowledge transfer','CON-KNOWTRANSFER'),
      ('10.1002/smj.2166','Independent boards and the institutional investors that prefer them','CON-INSTOWN'),
      ('10.1002/smj.2060','Why pure strategies may be wrong for transition economy firms','OTHER-CON'),
      ('10.1002/smj.4250040106','Technological evolution and competitive response','CON-TECHCHANGE'),
    ]
    for doi,title,term in titles:
        p=article(doi,title)
        ids={a['term_id'] for a in classify([p],TAX) if a['validation_status']=='validated_automatic'}
        if term!='OTHER-CON':assert term in ids,(doi,ids)
        assert 'TH-INSTIT' not in ids, 'Institutional investors alone do not prove institutional theory'


def test_institution_based_view_not_indiscriminately_institutional_theory():
    p=article('10.1002/smj.2060','Why pure strategies may be wrong for transition economy firms')
    extra=dict(paper_id=p['paper_id'],source_url='https://openalex.org/W123',
               abstract_hash='e'*64,abstract_available=True,
               abstract_phrase_hits=['TH-IBV','CON-COSTLEAD'],
               abstract_feature_method='allowed_phrase_occurrence_v7')
    assignments=classify([p],TAX,[extra])
    ids={a['term_id'] for a in assignments}
    assert 'TH-IBV' in ids and 'CON-COSTLEAD' in ids
    assert 'TH-INSTIT' not in ids
    assert 'OTHER-TH' not in ids and 'OTHER-CON' not in ids
    validate_taxonomy(TAX,assignments,[p])


def test_explicit_bower_burgelman_framework_is_different_from_generic_process():
    p=article('10.1002/smj.4250171011','Strategy making as iterated processes of resource allocation',1996)
    extra=dict(paper_id=p['paper_id'],source_url='https://openalex.org/W8',
               abstract_hash='f'*64,abstract_available=True,
               abstract_phrase_hits=['TH-BOWERBUR','CON-RESALLOC'],
               abstract_feature_method='allowed_phrase_occurrence_v7')
    rows=classify([p],TAX,[extra])
    ids={a['term_id'] for a in rows}
    assert 'TH-BOWERBUR' in ids and 'CON-RESALLOC' in ids
    record=enrich_papers([p],TAX,rows)[0]
    assert record['taxonomy_quality']['theory']['state']=='abstract_supported'


def test_differentiate_missing_abstract_stale_scan_and_current_no_match():
    papers=[article('10.1002/smj.'+str(i),'Unclassified archival investigation '+str(i))
            for i in range(1,4)]
    extra=[
      dict(paper_id=papers[0]['paper_id'],abstract_available=False),
      dict(paper_id=papers[1]['paper_id'],abstract_available=True,
           abstract_feature_method='allowed_phrase_occurrence_v6'),
      dict(paper_id=papers[2]['paper_id'],abstract_available=True,
           abstract_feature_method='allowed_phrase_occurrence_v7'),
    ]
    assignments=classify(papers,TAX,extra)
    rows=enrich_papers(papers,TAX,assignments)
    summary=coverage(rows,[],assignments,[],extra,{})
    for level in ('construct','theory'):
        report=summary['classification_by_dimension'][level]
        assert report['unresolved_other']==3
        assert report['unresolved_with_abstract']==2
        assert report['unresolved_without_abstract']==1
        assert report['unresolved_pending_feature_backfill']==1
        assert report['unresolved_after_current_abstract_scan']==1
        assert report['substantive_papers']==0
    assert summary['classification_by_dimension']['theory']['denominator']==3


def test_audit_ngram_dedup_and_decade_selection():
    assert 'market power' in ngrams('Market power matters. Market power rises.')
    assert 'firm performance' not in {x for x in ngrams('Firm performance')
           if meaningful(x,{'firm performance'})}
    papers=[article('10.1002/smj.'+str(i),'Research into organizations',1980+i*10)
            for i in range(1,5)]
    enriched={p['paper_id']:dict(openalex_id='https://openalex.org/W'+str(i),
                                abstract_available=True)
              for i,p in enumerate(papers)}
    pool,chosen=choose_papers(papers,enriched,[], 'construct',4)
    assert len(pool)==len(chosen)==4
    assert {p['publication_year'] for p in chosen}=={1990,2000,2010,2020}


def test_site_shows_unresolved_provenance_diagnostic():
    script=(ROOT/'src/scripts/research-app.ts').read_text(encoding='utf-8')
    for tag in ('unresolved_without_abstract','unresolved_pending_feature_backfill',
                'unresolved_after_current_abstract_scan'):
        assert tag in script
