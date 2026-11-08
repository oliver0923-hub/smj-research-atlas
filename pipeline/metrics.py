"""Prefer current per-paper v4 records when combining historical summary counts."""
from collections import Counter


def claim_counts(legacy,researches):
    processed={r['paper_id'] for r in researches}
    retained=[c for c in legacy if c['paper_id'] not in processed]
    counts=Counter(c['claim_type'] for c in retained)
    papers={c['paper_id'] for c in retained}
    for r in researches:
        local=Counter(h['kind'] for h in r['hypotheses'])
        local['finding']+=len(r['findings'])
        local.update(c['kind'] for c in r['checks'])
        counts.update(local)
        if sum(local.values()):papers.add(r['paper_id'])
    names={'hypothesis':'hypothesis_records','proposition':'proposition_records','finding':'finding_records',
           'robustness':'robustness_records','sensitivity':'sensitivity_records'}
    return dict({target:counts[source] for source,target in names.items()},
        study_claim_records=sum(counts.values()),study_claim_papers=len(papers),
        study_claim_count_scope='Preferred v4 per processed paper; historical v3 only for other papers; no double counting')
