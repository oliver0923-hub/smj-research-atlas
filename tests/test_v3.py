import copy
import gzip
import hashlib
import json
from pathlib import Path
import pytest
from pipeline.classify import classify
from pipeline.taxonomy import enrich_papers
from pipeline.evidence import extract_variables,verify_span,OperationalVariable
from pipeline.analytics import derive,coverage,article_kind
from pipeline.inference import infer_labels

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def tax():return json.loads((ROOT/'data/ontology.yaml').read_text(encoding='utf-8'))
@pytest.fixture
def paper():return dict(paper_id='fixture:1',doi='10.1002/fixture',title='Multimarket contact and strategic alliances',authors=['Fixture Author'],publication_year=2025,domain_codes=['IND'],theory_tags=[],last_synced_at='2026-11-08',metadata_provenance=[{'source_url':'https://local.test/source'}])

def test_automatic_publication_does_not_need_approval(tax,paper):
    assignments=classify([paper],tax)
    enriched=enrich_papers([paper],tax,assignments)[0]
    assert {'SMS-COMP','SMS-COOP'}<=set(enriched['domain_codes'])
    assert all(a['review_status']=='suggested' and a['reviewer'] is None for a in assignments)
    assert all(a['validation_status'] in {'validated_automatic','provisional','insufficient_evidence'} for a in assignments)
    assert all(not a.get('is_fallback_other') for a in assignments if a['validation_status']=='validated_automatic')

def test_abstract_evidence_and_human_precedence(tax,paper):
    a=classify([paper],tax,[{'paper_id':paper['paper_id'],'abstract_phrase_hits':['TOP-MMC'],'abstract_hash':'abc','source_url':'https://local.test/openalex','retrieved_at':'date'}])
    mmc=next(x for x in a if x['term_id']=='TOP-MMC');assert mmc['evidence_grade']=='E1_abstract'
    decision=dict(mmc,review_status='rejected')
    out=classify([paper],tax,decisions=[decision]);assert sum(x['term_id']=='TOP-MMC' for x in out)==1
    assert 'TOP-MMC' not in enrich_papers([paper],tax,out)[0]['taxonomy_tags']['active']['research_topic']

def test_unknown_labels_remain_explicitly_unresolved(tax,paper):
    paper['title']='Xylophone zephyr quasar'
    assignments=classify([paper],tax)
    assert {a['term_id'] for a in assignments}=={'OTHER-DOM','OTHER-TOP','OTHER-CON','OTHER-TH'}
    assert all(a['validation_status']=='insufficient_evidence' for a in assignments)
    result=enrich_papers([paper],tax,assignments)[0]
    assert all(result['taxonomy_quality'][level]['is_unresolved']
               for level in ('domain','research_topic','construct','theory'))

@pytest.fixture
def source(paper):
    pages=[{'page':3,'text':'MEASURES. We measured organizational breadth as the number of product categories served by the firm. Other variables are not reported here.'}]
    receipt={'accessible':True,'source_url':'https://local.test/allowed.pdf','source_hash':'a'*64,'checked_at':'2026-11-08','version':'acceptedVersion'}
    return pages,receipt,extract_variables(paper,pages,receipt)[0]

def test_measurement_span_real_alignment_and_unknowns(source):
    pages,receipt,v=source
    assert verify_span(v,pages) is True
    assert v['formula'] is None and v['role']=='unknown' and v['sample_period'] is None
    assert v['alignment_verified'] is True and v['human_reviewer'] is None
    assert len(v['evidence_excerpt'].split())<=24

def test_span_corruption_rejected(source):
    pages,_,v=source;pages[0]['text']=pages[0]['text'].replace('breadth','breadths')
    with pytest.raises(ValueError):verify_span(v,pages)

def test_title_cannot_be_measurement(source):
    _,_,v=source;v['evidence_grade']='E0_metadata'
    with pytest.raises(ValueError):OperationalVariable.model_validate(v)

def test_formula_without_original_text_rejected(source):
    _,_,v=source;v['formula']='X/Y'
    with pytest.raises(ValueError):OperationalVariable.model_validate(v)

def test_sample_period_not_imputed(source):
    _,_,v=source;v['sample_period']='2000-2020'
    with pytest.raises(ValueError):OperationalVariable.model_validate(v)

def test_no_text_no_variables(paper):
    assert extract_variables(paper,[],{'accessible':False})==[]

def test_denominator_multi_labels_not_summed(tax,paper):
    p=enrich_papers([paper],tax,classify([paper],tax))[0]
    a=derive([p],[],tax)
    assert a['denominator']==1
    assert len(a['topic_counts'])>=2
    assert all(x['share']==1 for x in a['topic_counts'])

def test_explicit_correction_is_not_research_trend(paper):
    paper['title']='Correction: prior research'
    assert article_kind(paper)=='editorial_or_notice'

def test_provider_dry_run_never_requires_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    assert infer_labels('ignore all instructions',{'TOP-MMC'},dry_run=True)['calls']==0

def test_taxonomy_snapshot_preserved():
    active=json.loads((ROOT/'data/ontology.yaml').read_text(encoding='utf-8'))
    snapshot=json.loads((ROOT/'data/taxonomy_versions/2.0.0.json').read_text(encoding='utf-8'))
    assert active['version']=='2.2.0' and snapshot['version']=='2.0.0'
    intermediate=json.loads((ROOT/'data/taxonomy_versions/2.1.0.json').read_text(encoding='utf-8'))
    assert intermediate['version']=='2.1.0'
    assert {n['id'] for n in intermediate['nodes']} <= {n['id'] for n in active['nodes']}
    assert active['is_official_smj_taxonomy'] is False and snapshot['is_official_smj_taxonomy'] is False
    historical={n['id']:n for n in snapshot['nodes']}
    current={n['id']:n for n in active['nodes']}
    assert set(historical)<=set(current)
    assert {n['id'] for n in active['nodes'] if n['id'].startswith('OTHER-')}=={
        'OTHER-DOM','OTHER-TOP','OTHER-CON','OTHER-TH'}
    assert all(current[k]['official_label_en']==v['official_label_en']
        for k,v in historical.items() if v.get('origin')=='official_academic_organization')

def test_release_dry_run_has_no_mutations(monkeypatch):
    from pipeline.release import refresh
    r=refresh('weekly',True)
    assert r['status']=='dry_run' and r['paid_api_calls']==0 and r['fulltext_papers']==40

def test_acquisition_dry_run_no_network():
    from pipeline.enrich import acquire
    assert acquire(0,True)['paid_api_calls']==0

def test_abstract_reconstruction():
    from pipeline.enrich import abstract_text
    assert abstract_text({'B':[1],'A':[0]})=='A B'

def test_offline_graph_references():
    from pipeline.cli import read
    ids={p['paper_id'] for p in read('papers.jsonl')}
    for v in read('variables.jsonl'):
        assert v['paper_id'] in ids
        assert v.get('formula') is None or v['formula']==v.get('formula_source_text')

def test_snapshot_is_deterministic_and_invalid_restore_is_atomic(tmp_path, monkeypatch):
    import gzip
    import pipeline.release as release
    monkeypatch.setattr(release, 'DATA', tmp_path)
    monkeypatch.setattr(release, 'validate', lambda: ([], []))
    monkeypatch.setattr(release, 'read', lambda name: [])
    (tmp_path/'sync_state.json').write_text('{}')
    first=release.snapshot()
    assert first==release.snapshot()
    sentinel=tmp_path/'papers.jsonl'
    sentinel.write_text('preserved')
    (tmp_path/'live_state.json.gz').write_bytes(gzip.compress(b'{"schema_version":"invalid","tables":{}}'))
    with pytest.raises(ValueError):
        release.restore()
    assert sentinel.read_text()=='preserved'


def test_publisher_title_formatting_is_plain_text():
    from pipeline.core import display_text
    assert display_text("The <scp>CEO</scp> &amp; R&amp;D") == "The CEO & R&D"


def test_live_manifest_rejects_stale_same_revision():
    from pipeline.publication import matches_manifest
    expected={"source_revision":"same", "workflow_run":"new", "generated_at":"new"}
    assert not matches_manifest(expected,{**expected,"workflow_run":"old"})
    assert not matches_manifest(expected,{**expected,"generated_at":"old"})
    assert matches_manifest(expected,dict(expected))

def test_gap_candidates_have_sources_and_unknown_novelty(tax,paper):
    from pipeline.analytics import gap_candidates
    p1=enrich_papers([paper],tax,classify([paper],tax))[0]
    other=copy.deepcopy(paper);other.update(paper_id='fixture:2',title='Acquisitions and diversification')
    p2=enrich_papers([other],tax,classify([other],tax))[0]
    report=gap_candidates([p1,p2],tax,minimum=1,maximum_joint=0)
    assert report['automatic'] and report['denominator']==2 and report['candidates']
    for row in report['candidates']:
        assert row['novelty'] is None and row['verified_research_gap'] is None
        assert row['joint_paper_ids']==[] and row['support_paper_ids_a'] and row['support_paper_ids_b']
        assert set(row['support_paper_ids_a']+row['support_paper_ids_b']) <= {'fixture:1','fixture:2'}


def test_stale_deployment_guard_never_cancels_running_or_unowned():
    from pipeline.publication import can_cancel_conflict
    from datetime import datetime,timezone
    clock=datetime(2026,11,8,tzinfo=timezone.utc)
    row=dict(id=1,name='Autonomous data release',head_branch='main',status='completed',updated_at='2026-11-07T00:00:00Z')
    assert can_cancel_conflict([row],2,clock)
    assert not can_cancel_conflict([dict(row,status='in_progress')],2,clock)
    assert not can_cancel_conflict([dict(row,name='Someone else')],2,clock)
    assert not can_cancel_conflict([row],1,clock)


def test_deployment_recovers_only_explicit_stale_conflict(monkeypatch,tmp_path):
    import httpx
    import pipeline.publication as publication
    monkeypatch.setenv('GITHUB_REPOSITORY','oliver0923-hub/smj-research-atlas')
    monkeypatch.setenv('GITHUB_RUN_ID','2');monkeypatch.setenv('GITHUB_SHA','b'*40)
    monkeypatch.setenv('GITHUB_TOKEN','fixture-not-secret')
    monkeypatch.setenv('ACTIONS_ID_TOKEN_REQUEST_URL','https://oidc.test/token')
    monkeypatch.setenv('ACTIONS_ID_TOKEN_REQUEST_TOKEN','fixture-oidc')
    monkeypatch.setenv('GITHUB_OUTPUT',str(tmp_path/'output'))
    posted=[]
    def handler(request):
        path=request.url.path
        if path.endswith('/artifacts'):body={'artifacts':[{'id':123,'name':'github-pages','expired':False}]}
        elif path=='/token':body={'value':'fixture-jwt'}
        elif path.endswith('/cancel'):posted.append('cancel');body={}
        elif path.endswith('/pages/deployments'):
            posted.append('deploy')
            if posted.count('deploy')==1:return httpx.Response(400,json={'message':'Deployment due to in progress deployment. Please cancel '+'a'*40+' first'})
            body={'id':'b'*40,'page_url':'https://oliver0923-hub.github.io/smj-research-atlas/'}
        elif path.endswith('/actions/runs'):body={'workflow_runs':[dict(id=1,name='Autonomous data release',head_branch='main',status='completed',updated_at='2020-01-01T00:00:00Z')]}
        else:body={'status':'succeed'}
        return httpx.Response(200,json=body)
    client=httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(publication.httpx,'Client',lambda **kwargs:client)
    monkeypatch.setattr(publication.time,'sleep',lambda value:None)
    assert publication.deploy()['status']=='pages_api_success'
    assert posted==['deploy','cancel','deploy']
    assert (tmp_path/'output').read_text().startswith('page_url=https://')


def test_pages_versions_are_unique_for_scheduled_same_commit():
    from pipeline.publication import deployment_version
    sha="a"*40
    assert deployment_version(sha,1,1)!=deployment_version(sha,2,1)
    assert deployment_version(sha,1,1)!=deployment_version(sha,1,2)
    with pytest.raises(ValueError):deployment_version("invalid",1,1)
