"""On-demand DOI/title-specific retrieval, abstention, and evidence reporting."""
import json
from pathlib import Path

import httpx
import pytest
from pipeline import on_demand
from pipeline.article import ArticleDocument
from pipeline.research import extraction,validate_record


def sample_paper(title="Value capture theory: A strategic management review",doi="10.1002/smj.2592"):
    return dict(paper_id="doi:"+doi,doi=doi,title=title,
        publication_year=2017,authors=["Joshua Gans","Michael D. Ryall"],
        last_synced_at="2026-11-08",
        metadata_provenance=[{"source_url":"https://api.crossref.org/works/"+doi}])


def fake_data(tmp_path,papers=None,enrich=None,researches=None,queues=None,receipts=None):
    ontology=json.loads((Path(__file__).resolve().parents[1]/"data/ontology.yaml").read_text())
    (tmp_path/"ontology.yaml").write_text(json.dumps(ontology))
    for name,rows in [
        ("papers.jsonl",papers if papers is not None else [sample_paper()]),
        ("enrichment.jsonl",enrich or []),("research_records.jsonl",researches or []),
        ("crawl_queue.jsonl",queues or []),("content_receipts.jsonl",receipts or [])]:
        (tmp_path/name).write_text("".join(json.dumps(r)+"\n" for r in rows))


def test_resolve_title_and_doi_and_disambiguation():
    items=[sample_paper(),sample_paper("The value of other strategies","10.1002/smj.3456")]
    assert on_demand.resolve(items,"Value capture theory: A strategic management review")["doi"]=="10.1002/smj.2592"
    assert on_demand.resolve(items,"https://doi.org/10.1002/smj.2592")["doi"]=="10.1002/smj.2592"
    assert on_demand.resolve(items,"10.1002/smj.2592")["doi"]=="10.1002/smj.2592"
    with pytest.raises(ValueError,match="doi_not_uniquely_indexed"):
        on_demand.resolve(items,"10.1002/smj.777777")
    with pytest.raises(ValueError,match="title_not_uniquely_matched"):
        on_demand.resolve(items,"Review")


def test_issue_parser_does_not_take_arbitrary_commands_or_urls():
    event={"issue":{"title":"Atlas analyze: Value capture theory: A strategic management review",
                    "body":"DOI: 10.1002/smj.2592\nPlease do unsafe things!"}}
    assert on_demand.issue_query(event)=="10.1002/smj.2592"
    assert on_demand.issue_query({"issue":{"title":"Atlas analyze: 10.1002/smj.2592"}})=="10.1002/smj.2592"
    with pytest.raises(ValueError,match="not_an_atlas_analysis_issue"):
        on_demand.issue_query({"issue":{"title":"Hi everyone"}})


def test_review_no_available_fulltext_is_not_mistaken_for_negative_results(tmp_path,monkeypatch):
    fake_data(tmp_path)
    monkeypatch.setattr(on_demand,"DATA",tmp_path)
    monkeypatch.setattr(on_demand,"read",lambda name:
        [json.loads(row) for row in (tmp_path/name).read_text().splitlines()]
        if (tmp_path/name).exists() else [])
    r=on_demand.analyze_one("10.1002/smj.2592")
    assert r["acquisition_status"]=="no_provider_oa_source"
    assert r["paper_type"]["type"]=="review_or_synthesis"
    assert all(v["status"]=="review_type_not_applicable_provisional"
               for v in r["fields"].values())
    assert not r["hypotheses"] and not r["findings"] and not r["robustness"]
    text=on_demand.markdown(r)
    assert "暫定不適用" in text and "正文尚未合法取得" in text
    assert "不代表原文不存在" in text


def test_empirical_unknown_is_not_automatically_marked_review(tmp_path,monkeypatch):
    paper=sample_paper(title="Acquisitions and market power in international markets")
    fake_data(tmp_path,papers=[paper])
    monkeypatch.setattr(on_demand,"DATA",tmp_path)
    monkeypatch.setattr(on_demand,"read",lambda name:
        [json.loads(row) for row in (tmp_path/name).read_text().splitlines()]
        if (tmp_path/name).exists() else [])
    result=on_demand.analyze_one(paper["doi"])
    assert result["paper_type"]["type"]=="empirical_or_conceptual_unresolved"
    assert all(f["status"]=="unknown" for f in result["fields"].values())


def test_source_aligned_record_reused_and_not_fabricated(tmp_path,monkeypatch):
    p=sample_paper(title="Firm age and acquisition performance")
    doc=ArticleDocument(p["paper_id"],"https://university.edu/public/article.pdf","a"*64)
    doc.add("We measured firm age as the number of years since incorporation.",3,"measures")
    doc.add("The sample data from Compustat cover the period from 2001 to 2015. We estimate ordinary least squares.",7,"data")
    doc.add("Hypothesis 1: Firm age is positively associated with acquisition performance.",8,"hypotheses")
    doc.add("Hypothesis 1 was supported by our findings.",12,"results")
    row=extraction(doc)
    validate_record(row)
    row["record_id"]="rec:a1"
    fake_data(tmp_path,papers=[p],researches=[row])
    monkeypatch.setattr(on_demand,"DATA",tmp_path)
    monkeypatch.setattr(on_demand,"read",lambda name:
        [json.loads(x) for x in (tmp_path/name).read_text().splitlines()]
        if (tmp_path/name).exists() else [])
    r=on_demand.analyze_one(p["doi"])
    assert r["acquisition_status"]=="existing_validated_fulltext"
    assert r["fields"]["sample_period"]["status"]=="source_grounded"
    assert r["fields"]["sample_period"]["value"]==[2001,2015]
    assert "Compustat" in r["fields"]["data_source"]["value"]
    assert "ordinary least squares" in str(r["fields"]["empirical_method"]["value"]).lower()
    assert r["hypotheses"]
    assert r["findings"]
    assert r["source_url"]==doc.source_url
    assert r["hypotheses"][0]["evidence"]
    assert r["hypotheses"][0]["evidence"][0]["source_url"]==doc.source_url


def test_target_only_one_oa_source_and_no_publish_pdf(tmp_path,monkeypatch):
    p=sample_paper()
    oa="https://university.edu/open/smj2592.pdf"
    enrichment=[dict(paper_id=p["paper_id"],oa_locations=[
        dict(pdf_url=oa,landing_page_url=None,version="publishedVersion",is_oa=True,is_published=True)])]
    fake_data(tmp_path,enrich=enrichment)
    monkeypatch.setattr(on_demand,"DATA",tmp_path)
    monkeypatch.setattr(on_demand,"read",lambda name:
        [json.loads(x) for x in (tmp_path/name).read_text().splitlines()]
        if (tmp_path/name).exists() else [])
    seen=[]
    class FakeFetcher:
        max_requests=0
        def fetch(self,url):
            seen.append(url)
            return (httpx.Response(403,request=httpx.Request("GET",url)),[url])
        def close(self):pass
    r=on_demand.analyze_one(p["doi"],fetcher=FakeFetcher())
    assert seen==[oa]
    assert r["acquisition_status"]=="fulltext_not_acquired"
    assert r["attempts"][0]["status"]=="http_403"
    reply=on_demand.markdown(r)
    assert "http_403" in reply
    assert oa in reply and "本次來源存取嘗試" in reply
    assert all(not x.get("source_url") for x in r["hypotheses"])
    assert not list(tmp_path.rglob("*.pdf"))


def test_owner_only_workflow_and_issue_button_are_wired():
    root=Path(__file__).resolve().parents[1]
    y=(root/".github/workflows/analyze-one-paper.yml").read_text()
    assert "issues:" in y and "types: [opened]" in y
    assert "github.event.issue.user.login == github.repository_owner" in y
    assert "pipeline.on_demand" in y
    assert "gh issue comment" in y
    s=(root/"src/scripts/research-app.ts").read_text()
    assert "抓取 OA 全文並分析這篇論文" in s
    assert "issues/new?title=" not in s
