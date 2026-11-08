# SMJ Atlas v2.2 — expanded constructs, theories, abstract viewer & Wiley OA PDFs

## Controlled vocabulary and quality

Atlas v2.2 retains **12 SMS-inspired Domain labels**, **20 existing Research Topic labels**, and adds over eighty explicit matching entries in the independent Construct and Theory axes, totaling 65 Construct and 37 Theory nodes including Other. The expanded concepts reflect recurring perspectives and empirical measures in strategic management (e.g. M&A, capabilities, network competition, multinationality, knowledge search, firm governance, entrepreneurial orientation). **These are Atlas editorial terms, not Wiley or SMS-authorized paper labels.** Parent relationships remain descriptive scope mappings, not proof that authors apply a particular theory.

A substantive Construct/Theory tag requires a conservative phrase match in a title or OpenAlex abstract-index feature. Topic/domain ancestors can be inherited from an explicit construct/topic. Theory is **never** imputed from a topic. Unknown gets `OTHER-CON` or `OTHER-TH`, not forced assignments. Source-grade scores are not calibrated academic precision estimates.

The original ontology is preserved under `data/taxonomy_versions/2.1.0.json`. Existing human-attested v2.0/v2.1 decisions are preserved.

## Show Abstract in each article's classification overview

At `/paper/?id=...`, the Research Classification Overview fetches a single abstract directly **on demand** via the public OpenAlex works API (`abstract_inverted_index`) and reconstructs it transiently inside the reader's browser. Full abstracts are **not** bundled in the static website JSON, Git history or downloadable CSV. The reader can navigate to the original DOI. OpenAlex does not own every abstract's copyright; the originating article/publisher retains associated rights. An unavailable, blocked, deleted or absent abstract displays a truthful fallback, never a fabricated abstract. Browser connectivity and cross-origin restrictions can prevent on-demand display.

The paper-search multi-select facet lists have an explicit **全部** option and a reset control, without deleting multi-label OR/AND filtering behavior.

## Published-open-access Wiley pdfdirect

For an SMJ DOI of the form `10.1002/smj.<number>`, `pipeline/wiley.py` creates `https://sms.onlinelibrary.wiley.com/doi/pdfdirect/{DOI}` **only if OpenAlex positively indicates publisher OA** (gold or hybrid; or a publisher-indexed OA published version). A green-only repository manuscript does NOT authorize assuming that the publisher original is public.

The usual crawler still uses URL/DNS/SSRF validation, robots checks, redirection policy, per-host rate limit and backoff, checks HTTP status, validates the downloaded PDF article identity and retains only extracted source-aligned evidence. It does not commit, redistribute or publish the PDF. Even a verified publisher-open PDF may be denied by the server from GitHub Actions. A bare, patterned DOI is never proof of rights.

The example `10.1002/smj.3735` is a real 2025 open-access SMJ paper by Lisa Tang, *Corporate development executives and M&A performance*, marked CC BY-NC-ND on the published PDF. The PDF is 41 pages and accessible to standard web retrieval as of 2026-11-08. This does NOT guarantee GitHub runners will be allowed to fetch it. The dedicated `Wiley OA real PDF smoke` workflow tests exactly that from a GitHub runner and records whether robots/403/other limitations prevented automated parsing; **neither smoke tests nor Atlas host copyrighted PDFs**.

## Tests and rollout

- `pytest tests/test_expanded_taxonomy_wiley.py tests/test_taxonomy_completeness.py`
- `pytest`
- `python -m pipeline.release gate`
- `npm run build`
- CI's Wiley OA smoke: `python -m pipeline.wiley_probe`
- Verify `data/coverage_report.json` counts and DOI-specific article page after live deployment.

Gradual taxonomy-index backfill uses `abstract_feature_method=allowed_phrase_occurrence_v5` and daily OpenAlex requests, keeping live work bounded. Historical papers not yet refreshed continue to show honest Other until their abstract feature index has been upgraded. Do not call this 100% concept accuracy.
