"""Evidence-first regression tests for hypotheses, results and sensitivity."""
import hashlib
import pytest
from pipeline.study import extract_study_claims,verify_claim,StudyClaim,STUDY_VERSION

def fixture():
    paper={'paper_id':'fixture:study','doi':'10.1002/smj.fixture','title':'Study results','authors':['Author']}
    source={
        'accessible':True,'source_url':'https://example.org/study.pdf',
        'source_hash':'a'*64,'checked_at':'2026-11-08'
    }
    pages=[
      {'page':4,'text':(
         'Hypothesis 1: Greater market overlap increases competitive restraint. '
         'Hypothesis 2: Resource scarcity reduces investment in innovation. '
         'This study concerns manufacturing firms.')},
      {'page':12,'text':(
         'The regression results support Hypothesis 1, and the coefficient is statistically significant at p < 0.05. '
         'Hypothesis 2 was not supported in the main specification. '
         'Hypothesis 1 and Hypothesis 2 were both mentioned in the appendix. '
         'Robustness checks showed that the core results remained robust to alternative firm size measures. '
         'Sensitivity analysis varied the estimation window but did not report its outcome.')},
    ]
    return paper,source,pages

def test_hypotheses_findings_robustness_and_sensitivity():
    paper,receipt,pages=fixture()
    claims=extract_study_claims(paper,pages,receipt)
    assert len([c for c in claims if c['claim_type']=='hypothesis'])==2
    assert len([c for c in claims if c['claim_type']=='finding'])==2
    assert len([c for c in claims if c['claim_type']=='robustness'])==1
    assert len([c for c in claims if c['claim_type']=='sensitivity'])==1
    h1=next(c for c in claims if c['hypothesis_label']=='H1' and c['claim_type']=='finding')
    h2=next(c for c in claims if c['hypothesis_label']=='H2' and c['claim_type']=='finding')
    assert h1['support_status']=='supported' and h1['significance']=='significant'
    assert h2['support_status']=='not_supported' and h2['significance']=='unknown'
    assert h1['related_hypothesis_id'] is not None
    assert next(c for c in claims if c['claim_type']=='robustness')['robustness_result']=='holds'
    assert next(c for c in claims if c['claim_type']=='sensitivity')['robustness_result']=='unknown'
    for c in claims:
        assert c['algorithm_version']==STUDY_VERSION
        assert c['source_hash']==receipt['source_hash']
        assert verify_claim(c,pages) is True

def test_no_inferred_significance_from_support_alone():
    paper,receipt,pages=fixture()
    finding=next(c for c in extract_study_claims(paper,pages,receipt) if c['hypothesis_label']=='H2')
    assert finding['significance']=='unknown'

def test_corrupted_source_is_rejected():
    paper,receipt,pages=fixture()
    claim=extract_study_claims(paper,pages,receipt)[0]
    pages[0]['text']=pages[0]['text'].replace('market overlap','market competition')
    with pytest.raises(ValueError,match='source-span mismatch'):
        verify_claim(claim,pages)

def test_cannot_claim_hypothesis_itself_is_significant():
    paper,receipt,pages=fixture()
    h=next(c for c in extract_study_claims(paper,pages,receipt) if c['claim_type']=='hypothesis')
    h['significance']='significant'
    with pytest.raises(ValueError):
        StudyClaim.model_validate(h)

def test_empty_source_does_not_generate_claims():
    paper,receipt,pages=fixture()
    assert extract_study_claims(paper,[],{'accessible':False})==[]
