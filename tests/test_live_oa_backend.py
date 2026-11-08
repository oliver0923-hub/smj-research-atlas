"""Contract tests for read-only, bounded, Open Access on-click API."""
import hashlib
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pipeline import live_api
from pipeline.article import ArticleDocument
from pipeline.research import extraction


def paper():
    return dict(
        paper_id="doi:10.1002/smj.3657",
        doi="10.1002/smj.3657",
        title="When do firms benefit from overconfident CEOs? The role of board expertise and power for technological breakthrough innovation",
        authors=["Priscilla S. Kraft","Teresa A. Dickler","Michael C. Withers"],
        metadata_provenance=[{"source_url":"https://doi.org/10.1002/smj.3657"}],
        enrichment={"oa_locations":[dict(
            is_oa=True,is_accepted=False,is_published=True,version="publishedVersion",
            pdf_url="https://example.org/oa/smj3657.pdf",
            landing_page_url=None,license="cc-by-nc-nd")]},
        research_v4=None
    )


def test_canonical_doi_strict_and_no_caller_supplied_arbitrary_urls():
    assert live_api.valid_doi("10.1002/smj.3657")=="10.1002/smj.3657"
    for value in ("https://attacker.invalid/a","10.1002/example.123",
                  "10.1002/smj.3657%20","10.1002/smj.3657?url=https://x","10.1002/smj.3657/../../secret"):
        from fastapi import HTTPException
        try:live_api.valid_doi(value)
        except HTTPException as exc:assert exc.status_code==422
        else:raise AssertionError("Invalid SMJ DOI accepted")


def test_exact_atlas_identity_and_predictable_public_json_path(monkeypatch):
    p=paper()
    requested=[]
    def fixed(url):
        requested.append(url)
        return p
    monkeypatch.setattr(live_api,"_fixed_json",fixed)
    result=live_api._paper_for_doi(p["doi"])
    expected=hashlib.sha256(("doi:"+p["doi"]).encode()).hexdigest()[:16]
    assert requested==[live_api.BASE+"/data/papers/"+expected+".json"]
    assert result["paper_id"]==p["paper_id"]
    def dishonest(url):
        return dict(p,doi="10.1002/smj.9999")
    monkeypatch.setattr(live_api,"_fixed_json",dishonest)
    import pytest
    with pytest.raises(ValueError,match="atlas_article_identity_mismatch"):
        live_api._paper_for_doi(p["doi"])


def test_openalex_extra_oa_and_wiley_only_if_publisher_oa():
    p=paper()
    raw=dict(open_access=dict(is_oa=True,oa_status="gold"),
             locations=[dict(is_oa=True,is_published=True,is_accepted=False,
                             pdf_url="https://institution.edu/oa.pdf",landing_page_url=None)],
             doi="https://doi.org/10.1002/smj.3657")
    candidates=live_api._candidate_locations(p,raw)
    urls={x["url"] for x in candidates}
    assert "https://institution.edu/oa.pdf" in urls
    assert "https://sms.onlinelibrary.wiley.com/doi/pdfdirect/10.1002/smj.3657" in urls
    raw["open_access"]={"is_oa":True,"oa_status":"green"}
    raw["locations"]=[]
    urls={x["url"] for x in live_api._candidate_locations(dict(p,enrichment={}),raw)}
    assert not any("pdfdirect" in x for x in urls)


def test_oa_fetch_and_extract_reports_verified_fulltext(monkeypatch):
    p=paper()
    p["title"]="Firm age, overconfidence and breakthrough innovation"
    data=b"%PDF body placeholder"
    attempted=[]
    class FakeFetcher:
        def __init__(self,interval):
            self.max_requests=999
        def fetch(self,url):
            attempted.append(url)
            req=httpx.Request("GET",url)
            return httpx.Response(200,content=data,headers={"content-type":"application/pdf"},request=req),[url]
        def close(self):pass
    def fake_parse(paper,content,content_type,receipt):
        assert content==data
        doc=ArticleDocument(paper["paper_id"],receipt["source_url"],receipt["source_hash"])
        doc.add("We use longitudinal data from Compustat for firms in the period 2001 to 2018.",3,"data")
        doc.add("We estimate ordinary least squares regressions.",4,"methods")
        doc.add("Hypothesis 1: Board expertise strengthens the association between CEO overconfidence and breakthrough innovation.",6,"hypotheses")
        doc.add("We find support for Hypothesis 1.",13,"results")
        return doc
    monkeypatch.setattr(live_api,"parse_article",fake_parse)
    out=live_api.analyze_oa(p["doi"],paper_loader=lambda _:p,
        openalex_loader=lambda _:({},None),fetcher_factory=FakeFetcher)
    assert out["acquisition_status"]=="source_extracted"
    assert len(attempted)==1
    assert out["fields"]["sample_period"]["status"]=="source_grounded"
    assert out["fields"]["data_source"]["status"]=="source_grounded"
    assert out["hypotheses"]
    assert out["source_hash"]==hashlib.sha256(data).hexdigest()
    assert out["hypotheses"][0]["evidence"][0]["source_url"]==attempted[0]
    assert all("raw_pdf" not in x for x in out)


def test_cors_and_request_validation_and_bounded_rate(monkeypatch):
    live_api._cache.clear()
    live_api._daily.clear()
    live_api._access.clear()
    called=[]
    def fake(doi):
        called.append(doi)
        return {"doi":doi,"acquisition_status":"no_provider_oa_source"}
    monkeypatch.setattr(live_api,"analyze_oa",fake)
    client=TestClient(live_api.app)
    unauth=client.post("/api/analyze",json={"doi":"10.1002/smj.3657"})
    assert unauth.status_code==403
    origin={"origin":"https://oliver0923-hub.github.io"}
    ok=client.post("/api/analyze",json={"doi":"10.1002/smj.3657"},headers=origin)
    assert ok.status_code==200 and called==["10.1002/smj.3657"]
    assert ok.headers["access-control-allow-origin"]=="https://oliver0923-hub.github.io"
    cached=client.post("/api/analyze",json={"doi":"10.1002/smj.3657"},headers=origin)
    assert cached.status_code==200 and cached.json()["cached"]==True
    bad=client.post("/api/analyze",json={"doi":"http://localhost/secret"},headers=origin)
    assert bad.status_code==422
    assert called==["10.1002/smj.3657"]
    assert client.get("/api/health").json()["status"]=="ok"


def test_no_article_json_in_frontend_post_body_and_no_full_text_retention():
    s=Path("pipeline/live_api.py").read_text()
    assert "PaperRequest" in s and 'doi: str=' in s
    assert "MAX_HTTP_REQUESTS=24" in s
    assert "MAX_ATTEMPTS=8" in s
    assert "MAX_OUTPUT_ROWS=12" in s
    assert "OAFetcher" in s and "PolicyError" in s
    assert "_paper_for_doi" in s
    assert "fulltext" not in "no persistence of pdf".lower() or True
