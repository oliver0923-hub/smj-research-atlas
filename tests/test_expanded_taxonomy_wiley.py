"""Expanded SMJ research coding, public abstract view, and publisher OA guardrails."""
import json
from pathlib import Path

from pipeline.classify import classify
from pipeline.taxonomy import enrich_papers, validate_taxonomy
from pipeline.crawl import locations
from pipeline.wiley import wiley_pdfdirect_candidate,merge_wiley_candidate

ROOT=Path(__file__).resolve().parents[1]
TAX=json.loads((ROOT/"data/ontology.yaml").read_text(encoding="utf-8"))


def paper(title="Corporate development executives and M&A performance"):
    return dict(paper_id="doi:10.1002/smj.3735",doi="10.1002/smj.3735",
                title=title,publication_year=2025,last_synced_at="2026-11-08",
                metadata_provenance=[{"source_url":"https://api.crossref.org/works/10.1002/smj.3735"}])


def test_expanded_constructs_theories_valid_and_historical_taxonomy_preserved():
    nodes=validate_taxonomy(TAX)
    assert TAX["version"]=="2.3.0"
    assert len([x for x in nodes.values() if x.level=="construct"])>=77
    assert len([x for x in nodes.values() if x.level=="theory"])>=45
    assert len([x for x in nodes.values() if x.level=="domain" and
                x.origin=="official_academic_organization"])==12
    assert (ROOT/"data/taxonomy_versions/2.1.0.json").exists()
    assert (ROOT/"data/taxonomy_versions/2.0.0.json").exists()


def test_new_construct_is_multilabeled_and_theory_is_independent():
    p=paper("Corporate development executives and M&A performance")
    e=dict(paper_id=p["paper_id"],source_url="https://openalex.org/W777",
           abstract_hash="a"*64,abstract_available=True,
           abstract_phrase_hits=["CON-CDEEXP","CON-ACQPERF","TH-OL"])
    rows=classify([p],TAX,[e])
    labels={r["term_id"] for r in rows}
    assert {"CON-CDEEXP","CON-ACQPERF","TOP-MNA","SMS-CORP","TH-OL"}<=labels
    assert not any(r["term_id"]=="OTHER-CON" for r in rows)
    assert not any(r["term_id"]=="OTHER-TH" for r in rows)
    assert all(r["evidence_grade"]=="E1_abstract" for r in rows
               if r["term_id"] in {"CON-CDEEXP","TH-OL"})
    quality=enrich_papers([p],TAX,rows)[0]["taxonomy_quality"]
    assert quality["construct"]["state"]=="abstract_supported"
    assert quality["theory"]["state"]=="abstract_supported"


def test_theory_not_invented_from_ma_topic():
    p=paper()
    ids={a["term_id"] for a in classify([p],TAX)}
    assert "TOP-MNA" in ids
    assert "OTHER-TH" in ids


def test_wiley_pdf_only_when_publisher_open_access_reported():
    doi="10.1002/smj.3735"
    raw={"open_access":{"is_oa":True,"oa_status":"hybrid"},"locations":[]}
    item=wiley_pdfdirect_candidate(doi,raw)
    assert item["pdf_url"]=="https://sms.onlinelibrary.wiley.com/doi/pdfdirect/"+doi
    assert item["is_oa"] and item["is_published"]
    assert item["candidate_origin"].startswith("OpenAlex")
    assert wiley_pdfdirect_candidate(doi,{"open_access":{"is_oa":True,"oa_status":"green"}}) is None
    assert wiley_pdfdirect_candidate(doi,{"open_access":{"is_oa":False,"oa_status":"closed"}}) is None
    assert wiley_pdfdirect_candidate("10.1234/unknown",raw) is None
    assert wiley_pdfdirect_candidate("10.1002/smj.3735/../../x",raw) is None


def test_publisher_source_supported_by_openalex_published_location():
    raw={"open_access":{"is_oa":True,"oa_status":"green"},"locations":[{
        "is_oa":True,"is_published":True,"source":{"homepage_url":"https://onlinelibrary.wiley.com"},
        "landing_page_url":"https://sms.onlinelibrary.wiley.com/doi/10.1002/smj.3735"
    }]}
    result=merge_wiley_candidate("10.1002/smj.3735",raw,[raw["locations"][0]])
    assert len(result)==2
    entry={"paper_id":"doi:10.1002/smj.3735","oa_locations":result}
    candidates=locations(entry)
    assert any(x["url"].endswith("/doi/pdfdirect/10.1002/smj.3735") for x in candidates)
    assert len(merge_wiley_candidate("10.1002/smj.3735",raw,result))==len(result)


def test_site_has_all_filter_and_on_demand_abstract_not_static_copyright_copy():
    s=(ROOT/"src/scripts/research-app.ts").read_text(encoding="utf-8")
    assert "[['','全部']" in s
    assert "全部／清除分類條件" in s
    assert "showAbstract(app,enriched,p.doi)" in s
    assert "https://api.openalex.org/works/" in s
    assert "abstract_inverted_index" in s
    assert "Wiley 已標記 OA 的原版 PDF" in s
    # The complete abstract is fetched directly in the viewer, not committed
    # to a static JSON corpus or reproduced by the publisher.
    assert "abstract_fulltext" not in (ROOT/"pipeline/enrich.py").read_text(encoding="utf-8")
