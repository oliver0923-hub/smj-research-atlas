import copy
import pytest
import httpx
from pipeline.core import normalize, upsert, Variable, doi_key
from pipeline.cli import request

@pytest.fixture
def raw():
    # Fixture DOI syntax only; fixtures are not published corpus records.
    return {'DOI':'10.1002/smj.12345','ISSN':['1097-0266'],'container-title':['Strategic Management Journal'],'title':['Fixture title'],'published':{'date-parts':[[2020]]},'author':[]}
def test_accept(raw): assert normalize(raw)['publication_year']==2020
def test_wrong_journal(raw):
    raw['ISSN']=['0000-0000']
    with pytest.raises(ValueError):normalize(raw)
def test_title_conflict(raw):
    raw['container-title']=['Other journal']
    with pytest.raises(ValueError):normalize(raw)
def test_dual_feed_idempotent(raw):
    first=normalize(raw); second=normalize(raw)
    assert upsert(first,second)==first
    assert len({p['paper_id']:p for p in [first,second]})==1
def test_curated_preserved(raw):
    old=normalize(raw);old.update(domain_codes=['BEH','ALL'],theory_tags=['ABV'],method_tags=['panel_fe','iv'],verification_status='fulltext_screened')
    raw['title']=['Updated title'];new=upsert(old,normalize(raw))
    assert new['title']=='Updated title'
    for key in ['domain_codes','theory_tags','method_tags','verification_status']:assert new[key]==old[key]
def test_measure_guard():
    with pytest.raises(ValueError):Variable(variable_id='x',paper_id='p',construct_en='c',role='independent',formula='x/y',extraction_method='abstract',verification_status='measurement_verified')
def test_llm_not_verified():
    with pytest.raises(ValueError):Variable(variable_id='x',paper_id='p',construct_en='c',role='independent',extraction_method='llm',verification_status='measurement_verified',source_url='https://doi.org/10.1002/smj.1',source_hash='abc',evidence_locator='page 2')
def test_human_requires_action():
    with pytest.raises(ValueError):Variable(variable_id='x',paper_id='p',construct_en='c',role='dependent',extraction_method='manual',verification_status='human_reviewed',source_url='url',source_hash='abc',evidence_locator='p2')
@pytest.mark.parametrize('doi',['10.example/example','placeholder','https://doi.org/10.example/example'])
def test_placeholder(doi):
    with pytest.raises(ValueError):doi_key(doi)
def test_null_missingness():
    v=Variable(variable_id='x',paper_id='p',construct_en='c',role='control',extraction_method='manual',missingness={'lag':'not_verified'})
    assert v.formula is None
def test_bad_year(raw):
    raw['published']={'date-parts':[[1700]]}
    with pytest.raises(ValueError):normalize(raw)
def test_http_failure():
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(403))) as client:
        with pytest.raises(httpx.HTTPStatusError):request(client,'https://local.test',{})
def test_retry(monkeypatch):
    monkeypatch.setattr('pipeline.cli.time.sleep',lambda _:None)
    codes=iter([429,500,200])
    def handle(req):
        code=next(codes);return httpx.Response(code,json={'message':{'items':[]}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:assert request(client,'https://local.test',{})=={'items':[]}

def test_export_preserves_provenance(raw, tmp_path, monkeypatch):
    import json
    import pipeline.cli as cli
    paper=normalize(raw)
    monkeypatch.setattr(cli,'ROOT',tmp_path)
    monkeypatch.setattr(cli,'DATA',tmp_path/'data')
    (tmp_path/'data').mkdir()
    (tmp_path/'data'/'ontology.yaml').write_text(json.dumps({'version':'test','is_official_smj_taxonomy':False,'sources':[],'nodes':[]}),encoding='utf-8')
    monkeypatch.setattr(cli,'read',lambda name:[paper] if name=='papers.jsonl' else [])
    cli.build()
    exported=json.loads((tmp_path/'public/data/papers.json').read_text(encoding='utf-8'))[0]
    assert exported['paper_id']==paper['paper_id']
    assert exported['metadata_provenance']==paper['metadata_provenance']

def test_failed_sync_preserves_published_data(raw,tmp_path,monkeypatch):
    from argparse import Namespace
    import pipeline.cli as cli
    monkeypatch.setattr(cli,'DATA',tmp_path)
    data=cli.lines([normalize(raw)]);(tmp_path/'papers.jsonl').write_text(data,encoding='utf-8')
    def outage(*args,**kwargs):raise RuntimeError('Fixture outage')
    monkeypatch.setattr(cli,'request',outage)
    with pytest.raises(RuntimeError):cli.sync(Namespace(backfill=False,max_pages=1,rows=100))
    assert (tmp_path/'papers.jsonl').read_text(encoding='utf-8')==data

def test_workflow_permissions_and_schedule():
    from pathlib import Path
    import yaml
    root=Path(__file__).resolve().parents[1]
    sync=yaml.safe_load((root/'.github/workflows/sync-metadata.yml').read_text(encoding='utf-8'))
    trigger=sync.get('on',sync.get(True))
    assert trigger['schedule'][0]['cron']=='23 2 * * *'
    deploy=yaml.safe_load((root/'.github/workflows/build-deploy.yml').read_text(encoding='utf-8'))
    assert deploy['permissions']['pages']=='write'
    assert deploy['permissions']['id-token']=='write'
