"""Adversarial prose: do not reverse hypothesis support or significance."""
import pytest
from pipeline.study import finding_status,extract_study_claims

@pytest.mark.parametrize('sentence,expected',[
    ('The evidence did not support Hypothesis 2.',('not_supported','unknown')),
    ('We did not find support for H1.',('not_supported','unknown')),
    ('H1 was not supported.',('not_supported','unknown')),
    ('H1 is unsupported.',('not_supported','unknown')),
    ('We find no support for H1.',('not_supported','unknown')),
    ('The results fail to support H1.',('not_supported','unknown')),
    ('The results support H1.',('supported','unknown')),
    ('We partially supported H1.',('partially_supported','unknown')),
    ('H1 was supported and significant.',('supported','significant')),
    ('H1 displayed no significant relationship.',('unknown','not_significant')),
    ('H1 was not statistically significant.',('unknown','not_significant')),
    ('H1 was insignificant.',('unknown','not_significant')),
    ('H1 is supported, p < 0.05.',('supported','significant')),
    ('H1 was supported, with p = 0.20.',('supported','unknown')),
])
def test_not_silently_reverse_results(sentence,expected):
    assert finding_status(sentence)==expected

def test_multiple_hypotheses_in_one_sentence_are_not_conflated():
    paper={'paper_id':'fixture:precision'}
    receipt={'accessible':True,'source_url':'https://example.org/oa.pdf',
             'source_hash':'a'*64,'checked_at':'2026-11-08'}
    pages=[{'page':3,'text':
        'Hypothesis 1 and Hypothesis 2 were both supported by the model. '
        'Hypothesis 3: Greater market contact reduces aggressive entry. '
        'Hypothesis 3 received no significant support.'}]
    items=extract_study_claims(paper,pages,receipt)
    assert all((c['hypothesis_label'] not in {'H1','H2'}) for c in items)
    assert any(c['label']=='H3' and c['claim_type']=='hypothesis' for c in items)
