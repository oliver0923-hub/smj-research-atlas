import copy
import json
from pathlib import Path

import pytest

from pipeline.taxonomy import Assignment, Term, validate_taxonomy, suggest_assignments, emerging_topics, enrich_papers

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def taxonomy():
    return json.loads((ROOT/'data/ontology.yaml').read_text(encoding='utf-8'))

@pytest.fixture
def paper():
    return dict(paper_id='fixture:one',title='Multimarket contact and strategic alliances',publication_year=2026,domain_codes=['IND'],theory_tags=['MMC'],metadata_provenance=[{'source_url':'https://local.test/record'}])

def test_sources_levels_and_sms_membership(taxonomy):
    nodes=validate_taxonomy(taxonomy)
    domains=[n for n in nodes.values() if n.level=='domain']
    assert len(domains)==12
    assert {n.label_en for n in domains}=={'Behavioral Strategy','Competitive Strategy','Cooperative Strategies','Corporate Strategy','Entrepreneurship and Strategy','Global Strategy','Knowledge and Innovation','Stakeholder Strategy','Strategic Human Capital','Strategic Leadership & Governance','Strategy Practice','Strategy Process'}
    assert all(n.origin=='official_academic_organization' for n in domains)
    assert not taxonomy['is_official_smj_taxonomy']

def test_no_fake_operational_variables_or_human_reviews(taxonomy):
    assert not any(n['level']=='operational_variable' for n in taxonomy['nodes'])
    assert all(n['reviewer'] is None and n['review_status']=='needs_review' for n in taxonomy['nodes'])

def test_theory_is_independent(taxonomy):
    node=next(n for n in taxonomy['nodes'] if n['level']=='theory')
    node['parent_ids']=['SMS-BEH']
    with pytest.raises(ValueError):validate_taxonomy(taxonomy)

def test_invalid_level_edge_rejected(taxonomy):
    node=next(n for n in taxonomy['nodes'] if n['level']=='construct')
    node['parent_ids']=['SMS-BEH']
    with pytest.raises(ValueError):validate_taxonomy(taxonomy)

def test_unknown_source_rejected(taxonomy):
    taxonomy['nodes'][0]['source_ids']=['invented-source']
    with pytest.raises(ValueError):validate_taxonomy(taxonomy)

def test_paper_multi_label_proposals_are_never_approved(taxonomy,paper):
    first=suggest_assignments([paper],taxonomy)
    assert first==suggest_assignments([paper],taxonomy)
    ids={a['term_id'] for a in first}
    assert {'TOP-MMC','TOP-ALL','SMS-COMP','SMS-COOP'}<=ids
    assert not any(a['term_id'].startswith(('CON-','TH-')) for a in first)
    assert all(a['origin']=='algorithmic' and a['review_status']=='suggested' and a['reviewer'] is None for a in first)

def test_official_domain_does_not_mean_official_paper_classification(taxonomy,paper):
    a=suggest_assignments([paper],taxonomy)[0]
    a['origin']='official_academic_organization'
    with pytest.raises(ValueError):Assignment.model_validate(a)

def test_approval_requires_human_event(taxonomy,paper):
    a=suggest_assignments([paper],taxonomy)[0]
    a['review_status']='approved'
    with pytest.raises(ValueError):Assignment.model_validate(a)

def test_rejected_suggestion_not_resurrected(taxonomy,paper):
    a=suggest_assignments([paper],taxonomy)[0]
    a.update(review_status='rejected',reviewer='Fixture reviewer',reviewed_at='2026-11-07',audit_log=[{'decision':'rejected','reviewer':'Fixture reviewer','human_attestation':True}])
    Assignment.model_validate(a)
    assert a['assignment_id'] not in {p['assignment_id'] for p in suggest_assignments([paper],taxonomy,[a])}

def test_legacy_not_silently_upgraded(taxonomy,paper):
    proposals=suggest_assignments([paper],taxonomy)
    enriched=enrich_papers([paper],taxonomy,proposals)[0]
    assert enriched['legacy_domain_codes']==['IND']
    assert enriched['legacy_theory_tags']==['MMC']
    assert enriched['domain_codes']==[] and enriched['theory_tags']==[]
    assert len(enriched['taxonomy_tags']['suggested']['domain'])==2
    assert paper['domain_codes']==['IND']

def test_emerging_topics_have_denominators_and_remain_suggestions(taxonomy,paper):
    papers=[dict(paper,paper_id='fixture:'+str(i),title='Quantum sensing advantage',publication_year=2026) for i in range(4)]
    papers += [dict(paper,paper_id='old:'+str(i),title='Established legacy research',publication_year=2018) for i in range(4)]
    candidates=emerging_topics(papers,taxonomy)
    assert candidates
    assert all(c['review_status']=='suggested' and c['origin']=='algorithmic' and c['proposed_parent_ids']==[] for c in candidates)
    assert all(c['recent_denominator']==4 and c['baseline_denominator']==4 for c in candidates)
    assert candidates==emerging_topics(papers,taxonomy)
    assert emerging_topics([],taxonomy)==[]

def test_operational_level_needs_real_measure(taxonomy):
    c=next(n for n in taxonomy['nodes'] if n['level']=='construct')
    variable=copy.deepcopy(c);variable.update(id='OP-example',level='operational_variable',parent_ids=[c['id']])
    with pytest.raises(ValueError):Term.model_validate(variable)

def test_version_mismatch_rejected(taxonomy):
    taxonomy['nodes'][0]['version']='1.0.0'
    with pytest.raises(ValueError):validate_taxonomy(taxonomy)

def test_manual_review_command_preserves_audit_and_blocks_regeneration(taxonomy,tmp_path,monkeypatch):
    from argparse import Namespace
    import pipeline.cli as cli
    from pipeline.core import normalize
    monkeypatch.setattr(cli,'ROOT',tmp_path);monkeypatch.setattr(cli,'DATA',tmp_path/'data')
    cli.DATA.mkdir()
    (cli.DATA/'ontology.yaml').write_text(json.dumps(taxonomy),encoding='utf-8')
    p=normalize({'DOI':'10.1002/smj.12345','ISSN':['1097-0266'],'container-title':['Strategic Management Journal'],'title':['Multimarket contact'],'published':{'date-parts':[[2020]]},'author':[]})
    (cli.DATA/'papers.jsonl').write_text(cli.lines([p]),encoding='utf-8')
    assignment=suggest_assignments([p],taxonomy)[0]
    args=Namespace(assignment_id=assignment['assignment_id'],decision='approve',reviewer='Fixture reviewer',note='Test-only simulated review',source_url='https://local.test/evidence',evidence_locator='Fixture section',human_attestation=False)
    with pytest.raises(ValueError):cli.review_classification(args)
    assert not (cli.DATA/'classifications.jsonl').exists()
    args.human_attestation=True;cli.review_classification(args)
    args.decision='reject';cli.review_classification(args)
    record=cli.read('classifications.jsonl')[0]
    assert record['review_status']=='rejected' and len(record['audit_log'])==2
    generated=json.loads((cli.DATA/'generated/classifications.json').read_text(encoding='utf-8'))
    assert sum(a['assignment_id']==record['assignment_id'] for a in generated)==1
    assert next(a for a in generated if a['assignment_id']==record['assignment_id'])['review_status']=='rejected'
