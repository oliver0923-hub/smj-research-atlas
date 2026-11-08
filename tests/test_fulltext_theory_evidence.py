"""Test source-aligned author-declared theory vs incidental text mentions.

Synthetic text is intentional: QA must never claim a downloaded paper says
something without independent source retrieval, offset and identity checks.
"""
import json
from pathlib import Path

from pipeline.article import ArticleDocument,digest,SECTIONS
from pipeline.research import EvidenceRegistry,extraction,validate_record
from pipeline.theory_evidence import extract_theories,THEORY_EXTRACTOR_VERSION
from pipeline.classify import classify
from pipeline.taxonomy import validate_taxonomy,enrich_papers
from pipeline.analytics import coverage
from pipeline.crawl import plan
from pipeline.research import EXTRACTOR_VERSION

TAX=json.loads((Path(__file__).resolve().parents[1]/"data/ontology.yaml").read_text())


def paper(title="Organizational adaptations and knowledge strategies"):
    return dict(paper_id="doi:10.1002/smj.test",doi="10.1002/smj.test",
                title=title,publication_year=2025,
                last_synced_at="2026-11-08",
                metadata_provenance=[{
                    "source_url":"https://api.crossref.org/works/10.1002/smj.test"}])


def document():
    p=paper()
    doc=ArticleDocument(p["paper_id"],"https://example.org/oa/article.pdf","a"*64)
    doc.add("The goals of this paper are to study strategic decisions.",1,"introduction")
    doc.add("We draw on the resource-based view to develop our hypotheses about competitive advantage.",2,"theoretical background")
    doc.add("Agency theory offers a contrasting explanation for the choices investigated here.",2,"theoretical background")
    doc.add("We do not use transaction cost economics for our main argument.",3,"hypotheses development")
    doc.add("We extend the knowledge-based view to develop our novel propositions.",3,"hypotheses development")
    doc.add("We apply stakeholder theory to explain organizational behavior.",4,"references")
    doc.add("We apply institutional theory to explain the observed data.",5,"results")
    return doc


def test_paperwide_theory_extraction_uses_only_scoped_source_spans():
    doc=document()
    registry=EvidenceRegistry(doc)
    rows,scope=extract_theories(doc,TAX,registry)
    found={r["term_id"]:r for r in rows}
    assert scope["status"]=="scanned"
    assert "theoretical background" in scope["scoped_sections"]
    assert found["TH-RBV"]["status"]=="author_declared_use"
    assert found["TH-KBV"]["status"]=="author_declared_use"
    assert found["TH-AGENCY"]["status"]=="mentioned_in_section"
    assert found["TH-TCE"]["status"]=="mentioned_in_section"
    assert "TH-INSTIT" not in found
    assert "TH-STAKE" not in found
    assert all(r["evidence_ids"] for r in rows)
    assert found["TH-RBV"]["page"]==2
    assert found["TH-RBV"]["source_hash"]==doc.source_hash
    assert registry.validate()
    assert THEORY_EXTRACTOR_VERSION=="fulltext-theory-v1"


def test_reference_lists_and_generic_sections_do_not_become_adopted_theories():
    doc=ArticleDocument("doi:test","https://example.org/source.pdf","b"*64)
    doc.add("We apply stakeholder theory to test this proposition.",1,"references")
    doc.add("We draw on institutional theory to explain this result.",2,"results")
    rows,coverage_scope=extract_theories(doc,TAX,EvidenceRegistry(doc))
    assert rows==[]
    assert coverage_scope["status"]=="no_identifiable_theory_sections"


def test_fulltext_author_declaration_replaces_theory_other_but_mentions_only_candidate():
    p=paper()
    doc=document()
    r=extraction(doc,taxonomy=TAX)
    assert validate_record(r) is True
    assert r["theory_search_coverage"]["scoped_blocks"]>=3
    rows=r["theory_evidence"]
    assert any(x["term_id"]=="TH-RBV" and x["status"]=="author_declared_use" for x in rows)
    assert r["source_hash"]==doc.source_hash
    assigned=classify([p],TAX,researches=[r])
    validate_taxonomy(TAX,assigned,[p])
    ids={a["term_id"] for a in assigned}
    assert {"TH-RBV","TH-KBV","TH-AGENCY","TH-TCE"}<=ids
    assert "OTHER-TH" not in ids
    formal=[a for a in assigned if a["term_id"]=="TH-RBV"]
    assert len(formal)==1
    assert formal[0]["validation_status"]=="validated_automatic"
    assert formal[0]["evidence_grade"]=="E2_fulltext_section"
    assert formal[0]["source_hash"]==doc.source_hash
    assert formal[0]["author_declared_use"] is True
    assert formal[0]["fulltext_evidence_ids"]
    candidate=next(a for a in assigned if a["term_id"]=="TH-AGENCY")
    assert candidate["validation_status"]=="semantic_candidate"
    assert candidate["is_semantic_candidate"] is True
    assert candidate["evidence_grade"]=="E2_fulltext_section"
    e=enrich_papers([p],TAX,assigned)[0]
    assert e["taxonomy_quality"]["theory"]["state"]=="fulltext_author_declared"
    assert set(e["taxonomy_tags"]["active"]["theory"])=={"TH-RBV","TH-KBV"}
    assert {"TH-AGENCY","TH-TCE"}<=set(e["taxonomy_tags"]["candidate"]["theory"])
    stats=coverage([e],[],assigned,[],[],{})
    assert stats["classification_by_dimension"]["theory"]["fulltext_author_declared"]==1
    assert stats["classification_by_dimension"]["theory"]["substantive_papers"]==1


def test_nonadoption_mentions_leave_other_and_do_not_fake_theory_use():
    p=paper()
    doc=ArticleDocument(p["paper_id"],"https://example.org/oa/article.pdf","c"*64)
    doc.add("Agency theory provides one possible explanation, but this paper does not invoke that lens.",2,"theoretical background")
    rec=extraction(doc,TAX)
    rows=classify([p],TAX,researches=[rec])
    ids={x["term_id"] for x in rows}
    assert "OTHER-TH" in ids
    assert "TH-AGENCY" in ids
    assert next(x for x in rows if x["term_id"]=="TH-AGENCY")["validation_status"]=="semantic_candidate"
    assert not any(x.get("author_declared_use") for x in rows)


def test_manual_rejection_cannot_be_reintroduced_by_fulltext_author_statement():
    p=paper()
    doc=document()
    rec=extraction(doc,TAX)
    rejected=dict(assignment_id="legacy:manual-reject-rbv",
        paper_id=p["paper_id"],term_id="TH-RBV",taxonomy_version="2.4.0",
        origin="algorithmic",method="attested-review",
        source_url=doc.source_url,evidence_locator="human rejection",
        input_hash=doc.source_hash,review_status="rejected",
        reviewer="Researcher",reviewed_at="2026-11-08",
        audit_log=[dict(decision="rejected",reviewer="Researcher",human_attestation=True)])
    rows=classify([p],TAX,decisions=[rejected],researches=[rec])
    assert len([x for x in rows if x["term_id"]=="TH-RBV"])==1
    assert rows[0]["review_status"]=="rejected"


def test_parser_recognizes_complex_theory_section_headers():
    assert SECTIONS.fullmatch("2 Theoretical Background")
    assert SECTIONS.fullmatch("3 Theory and Hypotheses Development")
    assert SECTIONS.fullmatch("4 Literature Review")
    assert SECTIONS.fullmatch("5 Conceptual Framework")


def test_reparse_priority_for_previously_successful_oa_after_extractor_change():
    old=dict(paper_id="doi:old",first_seen_at="2026-01-01",last_checked_at=None,
        sources=[dict(source_id="old",url="https://example.org/old.pdf",kind="previous_success",
          state="extraction_partial",cycle_attempted="cycle:x",
          parser_version="article-document-4.0",extractor_version="research-fields-4.0")])
    fresh=dict(paper_id="doi:new",first_seen_at="2026-11-08",last_checked_at=None,
        sources=[dict(source_id="new",url="https://example.org/new.pdf",kind="pdf_url",
          state="fetch_pending",cycle_attempted=None,
          parser_version=None,extractor_version=None)])
    ordered=plan([fresh,old],{"cycle_id":"cycle:x","extractor_upgrade_pending":True},2)
    assert [p["paper_id"] for p,s in ordered]==["doi:old","doi:new"]
    assert EXTRACTOR_VERSION=="research-fields-4.1-theory-source"


def test_reported_theory_evidence_requires_source_span_provenance():
    p=paper()
    doc=document()
    rec=extraction(doc,TAX)
    rec["theory_evidence"][0]["evidence_ids"]=["ev:does_not_exist"]
    try:validate_record(rec)
    except ValueError as exc:
        assert "Dangling relational evidence" in str(exc)
    else:
        raise AssertionError("A missing source proof must fail validation")
