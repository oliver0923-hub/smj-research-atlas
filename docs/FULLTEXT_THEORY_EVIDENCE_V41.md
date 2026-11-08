# Full-text theory evidence v4.1 — author-declared use versus mere mention

## Purpose and scope

Existing SMJ Atlas v2.4 often cannot classify Theory from the abstract: after the complete v7 Abstract backfill, 2,954 indexed papers with an available, recently scanned abstract still had no explicit Theory tag. This is not evidence that those papers are atheoretical. The next responsible strategy is to inspect **lawfully accessible full text**, particularly Introduction, Theory / Theoretical Background, Literature Review, Conceptual Framework, and Hypotheses Development.

**This release does NOT assert that a theory mentioned in the paper is necessarily adopted, correctly used, or causally supported.** It distinguishes:

- `author_declared_use`: the authors explicitly state in the same sentence that *we draw on*, *we apply*, *we adopt*, *our framework builds on*, etc. a named ontology theory. This is an automatically source-aligned **E2 fulltext author declaration**, not academic peer verification.
- `mentioned_in_section`: the named theory appears in a relevant discussion, but no local author declaration was identified. This is a **candidate only** and must not replace `OTHER-TH` if no other substantive Theory was found.
- `context_candidate`: a weak multi-word contextual lens signal in the relevant section, without a direct named-theory phrase. It is a **candidate only** and is NOT an embedding-based semantic claim.
- `no_identifiable_theory_sections`: a legally retrieved article was parsed but no sufficiently identifiable Theory/Introduction/Hypotheses blocks survived the parser. This is a parser scope limit, not "no theory".

Sources are restricted to OpenAlex/publisher-permitted OA routes under existing robots/rate-limit and SSRF/redirect checks. `pipeline/article.py` recognizes combined Theory + Hypotheses headings. References, bibliographies, methodological tables, results sections, and appendices cannot establish use. A nearby negation such as `we do not use X` does not create an author-declared label. Prior human rejections take precedence over any automatic inference.

## Evidence schema and downstream representation

- `pipeline/theory_evidence.py` extracts named theory phrases with paragraph-level source offsets, page, section, fulltext content hash and at most three bounded evidence references per theory. The existing `EvidenceRegistry` verifies those source spans and keeps only short per-paper excerpts; source files are not shipped to Pages.
- `pipeline/research.py` retains `theory_evidence` and `theory_search_coverage` within existing v4 research records and validates evidence IDs; `EXTRACTOR_VERSION` becomes `research-fields-4.1-theory-source`.
- `pipeline/classify.py` consumes active parsed OA records. Only `author_declared_use` creates a substantive Theory assignment (`evidence_grade=E2_fulltext_section`); mere theory mentions remain `semantic_candidate` with E2 provenance but **do not count** as source-supported classifications or turn off `OTHER-TH`.
- `pipeline/taxonomy.py` distinguishes `fulltext_author_declared` from existing `abstract_supported` and `title_supported`.
- `pipeline/analytics.py` reports E2 author-declaration paper counts; `pipeline/research.report` separately counts accessible parsed papers with scoped Theory sections, author-declared Theory and section-only mentions.
- The single-paper UI exposes a source-linked evidence panel and hypotheses *co-location* links only when an evidence record locates both theory and hypothesis in exactly the same block. Co-location is NOT proof of theory → hypothesis derivation.

## Source acquisition and incremental backfill

GitHub Pages remains a static site. This release does not provide direct institutional authentication or increase copyright-constrained publisher PDF access. An **extractor-version upgrade** requeues previously parsed open sources and prioritizes a bounded reparse before new sources; failures are retained in source ledgers and do not erase prior validated records. Existing persistent v4 records generally do NOT include raw cached paragraph text; those papers need source re-fetch before their Theory section can be scanned. Thus online fulltext Theory coverage may remain small even if the extraction code is ready.

No external Transformer weights or zero-shot NLI model are downloaded by the CI runner in this release. Context-based suggestions use bounded multi-word lexical cues, not statistically calibrated embeddings. An eventual semantic-NLI model should be introduced only with a manually annotated, independent evaluation sample that measures false Theory-adoption claims.

## Testing and known limitations

```bash
python -m pytest tests/test_fulltext_theory_evidence.py
python -m pytest
python -m pipeline.release gate
python -m pipeline.cli build
npm run build
```

The tests include source-hash alignment, explicit first-person use, unrelated mentions, negation, bibliography/results exclusion, reviewed rejection precedence, E2 versus candidate quality, missing-proof errors, and extractor upgrade priority. They use **synthetic text deliberately**, so passing tests is not a claim that a particular SMJ paper uses one of those theories. Real OA retrieval and academic semantic correctness remain separate verification goals.

### Academic grounding

- Grimmer, J., & Stewart, B. M. (2013). Text as data: The promise and pitfalls of automatic content analysis methods for political texts. *Political Analysis, 21*(3), 267–297. https://doi.org/10.1093/pan/mps028
- Ocasio, W. (1997). Towards an attention-based view of the firm. *Strategic Management Journal, 18*(S1), 187–206. This is an illustration of why a named theoretical lens must be anchored to an author’s argument, not inferred from topical similarity.
- Krippendorff, K. (2004). *Content Analysis: An Introduction to Its Methodology.* 2nd ed. SAGE. Framework for reproducible contextual coding and reliability.
