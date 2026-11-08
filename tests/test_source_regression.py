import json
from pipeline.cli import ROOT,read
from pipeline.research import validate_record


def test_real_smj3340_source_ratio_regression_from_validated_artifact():
    fixture=json.loads((ROOT/'evaluation/smj3340_regression.json').read_text())
    assert len(fixture['source_excerpt'].split())<=25
    records=[r for r in read('research_records.jsonl') if r['paper_id']=='doi:'+fixture['doi'] and r['source_hash']==fixture['source_hash']]
    assert records,'Restore the verified atlas-data artifact before running source regression checks'
    r=records[0];validate_record(r)
    variables=[v for v in r['variables'] if v['name'].lower()==fixture['construct'] and v['fields']['inferred_ratio']['value']]
    assert variables
    f=variables[0]['fields'];assert 'patent applications' in f['numerator']['value']
    assert 'new entrants' in f['denominator']['value']
    assert f['proxy']['value']!='number of new entrants'
    assert f['formula']['value'] is None and f['inferred_ratio']['status']==fixture['expected']['inferred_ratio_status']
    assert f['level_of_analysis']['value']==fixture['expected']['level_of_analysis']
    evidence={e['evidence_id']:e for e in r['evidence']}
    assert all(evidence[e]['page']==fixture['pdf_page'] for e in f['numerator']['evidence_ids'])


def test_relationship_subset_reports_abstentions_as_misses():
    r=json.loads((ROOT/'evaluation/relationship_results.json').read_text(encoding='utf-8'))
    assert r['papers']==3 and len(r['details'])==26
    for kind,counts in r['fields'].items():
        rows=[x for x in r['details'] if x['kind']==kind]
        assert counts['tp']==sum(x['expected'] in x['predicted'] for x in rows)
        assert counts['fn']==sum(x['expected'] not in x['predicted'] for x in rows)
        assert counts['abstentions']==sum(not x['predicted'] for x in rows)


def test_reviewed_page_scope_is_checked_for_each_reported_value():
    from pipeline.evaluate import scoped_values
    blocks={'b1':{'text':'We use OLS.'},'b2':{'text':'We use 2SLS.'}}
    evidence={'e1':dict(page=3,block_id='b1',start=0,end=11),
              'e2':dict(page=8,block_id='b2',start=0,end=12)}
    assert scoped_values('empirical_method',['OLS','2SLS'],['e1','e2'],evidence,blocks,[3])==['OLS']
