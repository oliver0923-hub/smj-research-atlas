# Research design, hypotheses, results and robustness (v3.1)

This is a **fully automatic, evidence-linked research exploration index**. It is **not** a peer-reviewed extraction of effect sizes, significance or publication-quality coded hypotheses.

## Record model

Each paper may contain zero or more records in `data/study_claims.jsonl`.

| Field | Interpretation |
| --- | --- |
| `claim_type` | `hypothesis`, `proposition`, `finding`, `robustness`, `sensitivity` |
| `label` / `hypothesis_label` | Explicit H1/H2a/P1 label in the source sentence |
| `statement_excerpt` | Short bounded original-text excerpt; **not necessarily the complete hypothesis** |
| `support_status` | `supported`, `not_supported`, `partially_supported`, `mixed`, `unknown` |
| `significance` | `significant`, `not_significant`, `mixed`, `unknown` |
| `robustness_result` | `holds`, `does_not_hold`, `mixed`, `unknown` |
| `variables` | Explicit links only; empty until variable/hypothesis mapping is sourced |
| `source_page`, `source_span_start`, `source_span_end`, `source_hash`, `span_hash` | Provenance and text alignment |
| `validation_status` | Source-span consistency, **not** a guarantee of correct substantive interpretation |

`Hypothesis support` and `statistical significance` are **independent dimensions**. A statistically significant coefficient can contradict the hypothesized direction. A sentence saying 'supported' does not prove p < .05. Unsupported and not significant are not synonyms. A robustness *check* being mentioned does not imply that conclusions remained robust.

All unobserved fields stay `unknown` or `null`. A paper with no extracted record is *not* a paper with no hypothesis, no empirical result, or no robustness analysis.

## Current deterministic automatic extraction

- Only explicit H/P identifiers and named results in source text are eligible.
- More than one different H label in the same sentence is skipped to avoid assigning one outcome to multiple hypotheses.
- Numeric p-values are not separated into sentence fragments.
- Sensitivity/robustness statements can be indexed, but results remain unknown without explicit language.
- Every claim must be aligned to the transient fulltext via source span and source hash before publication.
- Source manuscripts and PDFs are not redistributed.
- Conceptual propositions do not carry a significance status.

## Next-stage limitations

Equations, statistical tables, superscript significance markers, supplementary exhibits, multiple models, interaction directions, mediation tests, alternative hypotheses, qualitative propositions and cross-sentence reasoning are not comprehensively extracted. Stronger academic interpretation will require structured PDF tables and/or a bounded, source-citing language-model extraction stage with claim-level contradiction checks.

No human approval is required for autonomous publication. The site should always distinguish auto-indexed *evidence* from a verified scientific claim.

## Current implementation

- `pipeline/study.py`: source-anchored extractor and schema.
- `pipeline/enrich.py`: durable claims on successful fulltext parse.
- `pipeline/release.py`: versioned v3.1 snapshot; v3.0 migration fills only the new claim table with empty records, not invented claims.
- `pipeline/cli.py`: relational validation and per-paper publication.
- `src/scripts/research-app.ts`: visible per-paper records and source links.

