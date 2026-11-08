# SMJ Abstract gap audit v2.4 (2026-11-08)

## Research question
Why do thousands of SMJ papers still have an Other / undetermined Construct or Theory despite an available abstract? Is it lack of taxonomy concepts or a failure to identify author-used theory in the abstract?

## Actual source-backed audit
Source: durable `atlas-data` DOI bibliography + OpenAlex `abstract_inverted_index`. GitHub Actions run [42465047318](https://github.com/oliver0923-hub/smj-research-atlas/actions/runs/42465047318), using the public `pipeline.taxonomy_gap_audit` program on the pre-v2.4 data snapshot.

| Scope | In pre-update pool | Audited abstracts |
|---|---:|---:|
| Construct unresolved, OpenAlex abstract available | 2,847 | 480 |
| Theory unresolved, OpenAlex abstract available | 3,129 | 480 |
| Deduplicated union | — | **556 distinct abstracts** |

The sample uses decade-stratified stable DOI ordering, NOT a census, NOT an independent human-ground-truth benchmark, and not an estimate of precision, recall or construct/theory adoption. Only aggregate 2–4-gram counts and DOI/title examples leave the runner; entire copyrighted abstract text remains transient in memory.

### Representative repeated phrases and article checks

- `institutional investors` (6 documents): [SMJ DOI 10.1002/smj.2166](https://doi.org/10.1002/smj.2166), [10.1002/smj.3211](https://doi.org/10.1002/smj.3211).
- `technological change` (6): [10.1002/smj.2138](https://doi.org/10.1002/smj.2138), [10.1002/smj.4250040106](https://doi.org/10.1002/smj.4250040106).
- `bargaining power` (4): [10.1002/smj.3283](https://doi.org/10.1002/smj.3283).
- `institutional environment` (4): [10.1002/smj.3462](https://doi.org/10.1002/smj.3462).
- `cost leadership` (4): [10.1002/smj.2060](https://doi.org/10.1002/smj.2060).
- `local search` (4): [10.1002/smj.563](https://doi.org/10.1002/smj.563).
- `product innovation` (4): [10.1002/smj.3730](https://doi.org/10.1002/smj.3730).
- `market power` (3): [10.1002/smj.585](https://doi.org/10.1002/smj.585).
- `knowledge transfer` (3): [10.1002/smj.4250171108](https://doi.org/10.1002/smj.4250171108).

The **Theory** audit also identified `institution based view` (2, e.g. [10.1002/smj.2060](https://doi.org/10.1002/smj.2060)), `Bower Burgelman process model` (2; [10.1002/smj.4250171011](https://doi.org/10.1002/smj.4250171011) and [10.1002/smj.4250171012](https://doi.org/10.1002/smj.4250171012)), `stakeholder view` (3), `network theory` (2) and `resource based theory` (4 in construct audit).

IMPORTANT: repeated phrases such as `formal model`, `existing theories`, `theory and findings`, `theory managerial summary` are **not** theory names. They have not been promoted. Bibliographic contents like `Issue Information` and titles of nonresearch notices are excluded from the second audit. Mere phrase cooccurrence is evidence of a mention, not that the author adopted a particular lens.

## Engineering result

- **Version 2.4** contains 116 controlled Construct terms and 50 Theory terms (each includes one Other node), up from 77 and 45. Added 39 Constructs and 5 narrowly named theories/frameworks with editorial mappings. Existing official SMS Domain labels unchanged.
- Added distinct Concepts for institutional environment, institutional ownership, market/bargaining power, knowledge transfer, technological change, local search, product/process innovation, knowledge sharing, strategic groups, capital structure, social capital, governance modes, firm survival, etc.
- Theory changes emphasize explicit named frameworks (Institution-based View, Bower–Burgelman Process Model, Value Capture Theory, Strategic Group Theory, Relational Contracting Theory) and source-supported aliases, not generic topic inference.
- `abstract_feature_method=allowed_phrase_occurrence_v7` initiates bounded rescanning of older OpenAlex feature records. No full abstracts, PDFs, or copied source articles are published in the Atlas data file.
- `classification_by_dimension` now separately counts missing abstract, available abstract awaiting v7 reindex, and available abstract reindexed but no lexicon match. This distinguishes data access from concept noncoverage.
- All evidence-valid classifications remain separated from weak contextual suggestions (`semantic_candidate`). Neither is an independently verified academic assessment, and **Unknown means unestablished from our index, not absent in paper**.

## What remains unsolved

A theory is often introduced in Introduction / Theory Development rather than Abstract. Full-text access and actual author-use entailment remain essential for confident identification. It is not scientifically meaningful to set a 100% named-theory target by forcing a theory on every abstract. Construct mentions similarly do not validate variable operationalization or study role (IV/DV).

Topic modeling (LDA, BERTopic) can *suggest* clusters of missing concepts; clusters must be checked against explicit scholarly literature and then added to the editorial taxonomy before source-level paper labeling. It must not assign adopted-theory labels without evidence. The next stage should benchmark a stratified independently annotated sample (preferably 50–100 papers) and report multi-label per-dimension precision, recall, F1, and abstention rate.

## Academic references

- Blei, D. M., Ng, A. Y., & Jordan, M. I. (2003). Latent Dirichlet Allocation. *Journal of Machine Learning Research*, 3, 993–1022. https://www.jmlr.org/papers/v3/blei03a.html
- Grimmer, J., & Stewart, B. M. (2013). Text as Data: The Promise and Pitfalls of Automatic Content Analysis Methods for Political Texts. *Political Analysis*, 21(3), 267–297. https://doi.org/10.1093/pan/mps028
- Noda, T., & Bower, J. L. (1996). Strategy making as iterated processes of resource allocation. *Strategic Management Journal*, 17(S1), 159–192. https://doi.org/10.1002/smj.4250171011
- Burgelman, R. A. (1996). A process model of strategic business exit: Implications for an evolutionary perspective on strategy. *Strategic Management Journal*, 17(S1), 193–214. https://doi.org/10.1002/smj.4250171012

Reproducible CLI:
```bash
python -m pipeline.taxonomy_gap_audit --batches 24 --top 90
python -m pytest tests/test_taxonomy_abstract_audit_v24.py
```
