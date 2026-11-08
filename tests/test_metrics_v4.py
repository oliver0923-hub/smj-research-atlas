from pipeline.metrics import claim_counts


def test_current_paper_replaces_old_counts_without_dropping_other_legacy_papers():
    legacy=[dict(paper_id='a',claim_type='finding')]*10+[dict(paper_id='b',claim_type='finding')]
    records=[dict(paper_id='a',hypotheses=[dict(kind='hypothesis')],findings=[{}]*2,
                  checks=[dict(kind='robustness'),dict(kind='sensitivity')])]
    result=claim_counts(legacy,records)
    assert result['finding_records']==3
    assert result['hypothesis_records']==1
    assert result['robustness_records']==result['sensitivity_records']==1
    assert result['study_claim_records']==6 and result['study_claim_papers']==2
