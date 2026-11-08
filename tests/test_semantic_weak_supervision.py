"""Weak title / abstract classification candidate separation and coverage gates."""
import json
from pathlib import Path
from pipeline.semantic import hits_for_text,title_hits,FEATURE_VERSION
from pipeline.classify import classify
from pipeline.taxonomy import validate_taxonomy,enrich_papers
from pipeline.analytics import coverage
ROOT=Path(__file__).resolve().parents[1]
TAX=json.loads((ROOT/'data/ontology.yaml').read_text(encoding='utf-8'))


def paper(title='A longitudinal archival analysis of several organizations'):
    return dict(paper_id='doi:10.1002/smj.fixture',doi='10.1002/smj.fixture',
        title=title,publication_year=2025,last_synced_at='2026-11-08',
        metadata_provenance=[{'source_url':'https://api.crossref.org/works/10.1002/smj.fixture'}])


def test_versioned_ontology_and_no_official_reinterpretation():
    nodes=validate_taxonomy(TAX)
    assert TAX['version']=='2.3.0'
    assert len([n for n in nodes.values() if n.level=='construct'])==77
    assert len([n for n in nodes.values() if n.level=='theory'])==45
    assert FEATURE_VERSION=='smj-context-features-v1'
    assert (ROOT/'data/taxonomy_versions/2.2.0.json').exists()
    assert len([n for n in nodes.values() if n.level=='domain'
                and n.origin=='official_academic_organization'])==12


def test_context_weak_supervision_recognizes_focused_multiword_cues():
    abstract=('We examine patent applications, financial slack, and '
              'performance shortfalls using a resource based perspective.')
    hits=hits_for_text(abstract,TAX)
    ids={h['term_id'] for h in hits}
    assert {'CON-PATINTENSITY','CON-SLACK','CON-PERFFDBK','TH-RBV'}<=ids
    assert all(h['status']=='candidate_not_verified' for h in hits)
    assert all(' ' in h['trigger'] for h in hits)
    assert 'TH-AGENCY' not in ids


def test_negative_and_generic_words_do_not_infer_theory():
    assert not any(h['term_id']=='TH-RBV' for h in hits_for_text(
        'We do not rely on a resource based perspective in this analysis.',TAX))
    assert not any(h['dimension']=='theory' for h in hits_for_text(
        'We test innovation, mergers, risk and firm performance.',TAX))
    assert title_hits('Mergers and technological change',TAX)==[]


def test_weak_candidates_not_classified_as_author_used_theories_or_measured_constructs():
    p=paper()
    extra=dict(paper_id=p['paper_id'],abstract_available=True,
        abstract_hash='a'*64,openalex_id='https://openalex.org/W1234',
        source_url='https://openalex.org/W1234',retrieved_at='2026-11-08',
        abstract_weak_hits=hits_for_text(
            'Using patent applications, we describe a resource based perspective.',TAX))
    a=classify([p],TAX,[extra])
    assert {'CON-PATINTENSITY','TH-RBV'}<={r['term_id'] for r in a
                                          if r.get('is_semantic_candidate')}
    assert all(r['validation_status']=='semantic_candidate' for r in a
               if r.get('is_semantic_candidate'))
    assert {r['term_id'] for r in a if r.get('is_fallback_other')}=={
        'OTHER-DOM','OTHER-TOP','OTHER-CON','OTHER-TH'}
    validate_taxonomy(TAX,a,[p])
    result=enrich_papers([p],TAX,a)[0]
    assert result['taxonomy_tags']['active']['theory']==['OTHER-TH']
    assert result['taxonomy_tags']['active']['construct']==['OTHER-CON']
    assert result['taxonomy_tags']['candidate']['theory']==['TH-RBV']
    assert result['taxonomy_tags']['candidate']['construct']==['CON-PATINTENSITY']
    assert result['taxonomy_quality']['construct']['is_unresolved']
    report=coverage([result],[],a,[],[extra],{})
    assert report['classification_by_dimension']['theory']['substantive_papers']==0
    assert report['classification_by_dimension']['theory']['additional_candidate_only_papers']==1
    assert report['classification_by_dimension']['construct']['additional_candidate_only_papers']==1
    assert report['classified_papers']==0


def test_explicit_abstract_evidence_overrides_weak_candidate_for_same_theory():
    p=paper()
    e=dict(paper_id=p['paper_id'],abstract_hash='a'*64,source_url='https://openalex.org/W5',
           abstract_phrase_hits=['TH-RBV'],abstract_weak_hits=[dict(
               term_id='TH-RBV',dimension='theory',source='abstract_context',
               trigger='rbv perspective',method='multiword_contextual_phrase_v1',
               heuristic_score=.54)])
    a=classify([p],TAX,[e])
    selected=[v for v in a if v['term_id']=='TH-RBV']
    assert len(selected)==1
    assert selected[0]['validation_status']=='validated_automatic'
    assert selected[0]['evidence_grade']=='E1_abstract'
    assert not selected[0].get('is_semantic_candidate')


def test_candidate_views_on_public_website():
    s=(ROOT/'src/scripts/research-app.ts').read_text(encoding='utf-8')
    assert '弱監督候選（不可視為作者使用理論）' in s
    assert '可能相關的構念／理論視角' in s
    assert 'additional_candidate_only_papers' in s
