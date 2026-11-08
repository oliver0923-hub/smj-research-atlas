"""Every indexed paper has four visible taxonomy dimensions without invented claims."""
import json
from pathlib import Path

from pipeline.classify import classify
from pipeline.taxonomy import validate_taxonomy, enrich_papers

ROOT=Path(__file__).resolve().parents[1]
TAX=json.loads((ROOT/"data/ontology.yaml").read_text(encoding="utf-8"))


def paper(title,pid="doi:10.1002/test"):
    return {"paper_id":pid,"doi":"10.1002/test","title":title,"publication_year":2026,
            "metadata_provenance":[{"source_url":"https://api.crossref.org/works/10.1002/test"}],
            "last_synced_at":"2026-11-08"}


def test_ontology_keeps_twelve_sms_domains_and_four_explicit_other_terms():
    nodes=validate_taxonomy(TAX)
    assert TAX["version"]=="2.1.0"
    official=[n for n in nodes.values() if n.level=="domain" and n.origin=="official_academic_organization"]
    assert len(official)==12
    assert {i for i in ("OTHER-DOM","OTHER-TOP","OTHER-CON","OTHER-TH")}<=set(nodes)
    assert nodes["OTHER-TOP"].parent_ids==["OTHER-DOM"]
    assert nodes["OTHER-CON"].parent_ids==["OTHER-TOP"]
    assert nodes["OTHER-TH"].parent_ids==[]


def test_no_evidence_means_all_four_dimensions_other_not_faked():
    p=paper("An unexplained analysis of a special archival collection")
    assignments=classify([p],TAX)
    got={a["term_id"] for a in assignments}
    assert got=={"OTHER-DOM","OTHER-TOP","OTHER-CON","OTHER-TH"}
    assert all(a["validation_status"]=="insufficient_evidence" for a in assignments)
    assert all(a["is_fallback_other"] and a["review_status"]=="suggested" for a in assignments)
    assert all(a["reviewer"] is None for a in assignments)
    validate_taxonomy(TAX,assignments,[p])
    r=enrich_papers([p],TAX,assignments)[0]
    assert {level:r["taxonomy_tags"]["active"][level] for level in
            ("domain","research_topic","construct","theory")}=={
        "domain":["OTHER-DOM"],"research_topic":["OTHER-TOP"],
        "construct":["OTHER-CON"],"theory":["OTHER-TH"]}
    assert all(v["state"]=="unresolved_other" for v in r["taxonomy_quality"].values())
    assert all(not v["substantive_terms"] for v in r["taxonomy_quality"].values())


def test_title_based_topic_and_domain_do_not_invent_theory_or_construct():
    p=paper("Multimarket contact and strategic alliances")
    assigned=classify([p],TAX)
    ids={a["term_id"] for a in assigned}
    assert {"TOP-MMC","TOP-ALL","SMS-COMP","SMS-COOP","OTHER-CON","OTHER-TH"}<=ids
    assert "OTHER-DOM" not in ids and "OTHER-TOP" not in ids
    r=enrich_papers([p],TAX,assigned)[0]
    assert r["taxonomy_quality"]["domain"]["state"]=="title_supported"
    assert r["taxonomy_quality"]["research_topic"]["state"]=="title_supported"
    assert r["taxonomy_quality"]["construct"]["state"]=="unresolved_other"
    assert r["taxonomy_quality"]["theory"]["state"]=="unresolved_other"


def test_abstract_construct_and_theory_link_to_editorial_ancestors():
    p=paper("Organizational research examined from a longitudinal perspective")
    e={"paper_id":p["paper_id"],"abstract_available":True,
       "abstract_phrase_hits":["CON-SLACK","TH-RBV"],
       "abstract_hash":"a"*64,"source_url":"https://openalex.org/W1",
       "retrieved_at":"2026-11-08"}
    assigned=classify([p],TAX,[e])
    ids={a["term_id"] for a in assigned}
    assert {"CON-SLACK","TOP-RESOURCE","SMS-CORP","SMS-KI","SMS-COMP","TH-RBV"}<=ids
    assert not any(a["is_fallback_other"] for a in assigned)
    assert all(a["validation_status"]=="validated_automatic" for a in assigned)
    r=enrich_papers([p],TAX,assigned)[0]
    for level in ("domain","research_topic","construct","theory"):
        assert r["taxonomy_quality"][level]["state"]=="abstract_supported"
        assert r["taxonomy_quality"][level]["best_evidence_grade"]=="E1_abstract"


def test_theory_is_independent_not_an_automatic_topic_or_domain():
    p=paper("Undisclosed evaluation of corporate archives")
    e={"paper_id":p["paper_id"],"abstract_available":True,
       "abstract_phrase_hits":["TH-RDT"],"abstract_hash":"b"*64,
       "source_url":"https://openalex.org/W2"}
    ids={a["term_id"] for a in classify([p],TAX,[e])}
    assert ids=={"TH-RDT","OTHER-DOM","OTHER-TOP","OTHER-CON"}


def test_fallback_does_not_count_as_substantive_taxonomy_classification():
    from pipeline.analytics import coverage
    p=paper("An unexplained analysis of a special archival collection")
    a=classify([p],TAX)
    record=enrich_papers([p],TAX,a)
    result=coverage(record,[],a,[],[],{})
    assert result["classified_papers"]==0
    for level in ("domain","research_topic","construct","theory"):
        assert result["classification_by_dimension"][level]["unresolved_other"]==1
        assert result["classification_by_dimension"][level]["substantive_papers"]==0
    assert result["taxonomy_coverage_papers_all_dimensions"]==0


def test_no_abstract_phrase_just_from_presence_of_abstract():
    p=paper("Research on academic knowledge boundaries")
    e={"paper_id":p["paper_id"],"abstract_available":True,
       "abstract_phrase_hits":[],"abstract_hash":"c"*64,
       "source_url":"https://openalex.org/W3"}
    tags=classify([p],TAX,[e])
    assert all(a["evidence_grade"]=="E0_metadata" for a in tags)


def test_historical_human_decision_does_not_reenable_rejected_topic():
    p=paper("Multimarket contact")
    manual={"assignment_id":"historical:test","paper_id":p["paper_id"],
            "term_id":"TOP-MMC","taxonomy_version":"2.0.0","origin":"algorithmic",
            "method":"historical fixture","source_url":"https://api.crossref.org/works/x",
            "evidence_locator":"historical record","input_hash":"xyz",
            "review_status":"rejected","reviewer":"Fixture Reviewer","reviewed_at":"2026-11-07",
            "audit_log":[{"decision":"rejected","reviewer":"Fixture Reviewer",
                          "human_attestation":True}]}
    assigned=classify([p],TAX,decisions=[manual])
    validate_taxonomy(TAX,assigned,[p])
    active={a["term_id"] for a in assigned if a["review_status"]!="rejected"}
    assert "TOP-MMC" not in active
    assert "OTHER-TOP" in active
