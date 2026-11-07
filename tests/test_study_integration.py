"""Migration, provenance and referential integrity of v3.1 study claims."""
import gzip
import json
from pathlib import Path
import pytest
from pipeline import cli,release
from pipeline.study import extract_study_claims

def dump(path,items):
    path.write_text(''.join(json.dumps(x)+'\n' for x in items),encoding='utf-8')

def test_restore_old_v3_snapshot_without_losing_papers(tmp_path,monkeypatch):
    tables={name:[] for name in release.TABLES if name!='study_claims.jsonl'}
    payload={'schema_version':'3.0.0','tables':tables,'state':{'last_successful_sync':'old'},
             'publisher_check':{},'checkpoints':{}}
    (tmp_path/'live_state.json.gz').write_bytes(gzip.compress(json.dumps(payload).encode()))
    monkeypatch.setattr(release,'DATA',tmp_path)
    monkeypatch.setattr(release,'read',lambda name:[])
    assert release.restore()['status']=='restored'
    assert (tmp_path/'study_claims.jsonl').exists()
    assert (tmp_path/'study_claims.jsonl').read_text()==''
    assert json.loads((tmp_path/'sync_state.json').read_text())['last_successful_sync']=='old'

def test_claim_source_hash_must_match_current_receipt(tmp_path,monkeypatch):
    monkeypatch.setattr(cli,'DATA',tmp_path)
    doi='10.1002/smj.3340'
    paper={'paper_id':'doi:'+doi,'doi':doi,'title':'Test','authors':['Test Author'],
           'publication_year':2020,'journal_issn':['1097-0266'],
           'metadata_provenance':[{'source':'fixture'}]}
    receipt={'paper_id':paper['paper_id'],'accessible':True,
             'source_url':'https://example.org/paper.pdf','source_hash':'a'*64,
             'checked_at':'2026-11-08'}
    page=[{'page':1,'text':'Hypothesis 1: Firms with more slack invest in new technology.'}]
    claim=extract_study_claims(paper,page,receipt)[0]
    dump(tmp_path/'papers.jsonl',[paper])
    dump(tmp_path/'variables.jsonl',[])
    dump(tmp_path/'content_receipts.jsonl',[receipt])
    dump(tmp_path/'study_claims.jsonl',[claim])
    cli.validate()
    claim['source_hash']='b'*64
    dump(tmp_path/'study_claims.jsonl',[claim])
    with pytest.raises(ValueError,match='Study claim source does not match'):
        cli.validate()

def test_no_duplicate_claim_ids_or_invalid_links(tmp_path,monkeypatch):
    monkeypatch.setattr(cli,'DATA',tmp_path)
    doi='10.1002/smj.3340'
    paper={'paper_id':'doi:'+doi,'doi':doi,'title':'Test','authors':['Test Author'],
           'publication_year':2020,'journal_issn':['1097-0266'],
           'metadata_provenance':[{'source':'fixture'}]}
    receipt={'paper_id':paper['paper_id'],'accessible':True,
             'source_url':'https://example.org/paper.pdf','source_hash':'a'*64,
             'checked_at':'2026-11-08'}
    page=[{'page':1,'text':'Hypothesis 1: Firms with more slack invest in new technology.'}]
    claim=extract_study_claims(paper,page,receipt)[0]
    dump(tmp_path/'papers.jsonl',[paper])
    dump(tmp_path/'variables.jsonl',[])
    dump(tmp_path/'content_receipts.jsonl',[receipt])
    dump(tmp_path/'study_claims.jsonl',[claim,claim])
    with pytest.raises(ValueError,match='Duplicate/dangling'):
        cli.validate()
