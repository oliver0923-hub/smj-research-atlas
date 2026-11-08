"""No-network tests for the autonomous metadata-to-fulltext scheduling flow."""
from datetime import datetime, timedelta, timezone
import json
import pytest
from pipeline.selection import safe_url, source_candidates, choose_papers, retry_reason
from pipeline import enrich


def location(url="https://research.example.edu/article.pdf", **updates):
    row={"is_oa":True,"is_accepted":True,"is_published":False,
         "pdf_url":url,"landing_page_url":"https://research.example.edu/item/1",
         "license":"cc-by","version":"acceptedVersion"}
    row.update(updates)
    return row


def entry(pid,loc=None):
    return {"paper_id":pid,"oa_locations":[loc or location()]}


def test_sources_include_pdf_and_landing_fallback():
    rows=source_candidates([location(),location(pdf_url="https://sms.onlinelibrary.wiley.com/file.pdf")])
    urls=[r["url"] for r in rows]
    assert urls[0]=="https://research.example.edu/article.pdf"
    assert "https://research.example.edu/item/1" in urls
    assert "https://sms.onlinelibrary.wiley.com/file.pdf" in urls
    assert len(urls)==3
    assert rows[0]["kind"]=="pdf_url"


@pytest.mark.parametrize("url",[
    "http://example.com/paper.pdf","https://localhost/private",
    "https://127.0.0.1/paper.pdf","https://169.254.169.254/latest",
    "https://10.3.4.5/content","https://example.local/file.pdf",
    "https://u:password@example.com/file.pdf","ftp://example.org/file.pdf"
])
def test_unsafe_sources_rejected(url):
    assert not safe_url(url)


def test_failed_403_is_cooled_down_but_new_oa_location_reopens():
    now=datetime(2026,11,8,tzinfo=timezone.utc)
    e=entry("p:one")
    previous={"accessible":False,"checked_at":(now-timedelta(days=1)).isoformat(),
              "failures":[{"url":"https://research.example.edu/article.pdf","reason":"HTTPStatusError:403"},
                          {"url":"https://research.example.edu/item/1","reason":"HTTPStatusError:403"}]}
    assert retry_reason(e,previous,"measure-v1","study-v1",current=now) is None
    updated=entry("p:one",location("https://another.edu/accepted.pdf"))
    assert retry_reason(updated,previous,"measure-v1","study-v1",current=now)=="new_oa_location"
    assert retry_reason(e,previous,"measure-v1","study-v1",current=now+timedelta(days=61))=="retry_after_cooldown"


def test_prefer_new_recent_papers_and_outdated_parser():
    now=datetime(2026,11,8,tzinfo=timezone.utc)
    papers={"new":{"publication_year":2026},
            "old-new":{"publication_year":2001},
            "upgrade":{"publication_year":2024},
            "fail":{"publication_year":2023}}
    rows=[entry(pid) for pid in papers]
    old={"upgrade":{"accessible":True,"extraction_algorithm_version":"old",
                    "study_algorithm_version":"old"},
         "fail":{"accessible":False,"checked_at":now.isoformat(),
                 "failures":[{"url":"https://research.example.edu/article.pdf","reason":"HTTPStatusError:403"},
                             {"url":"https://research.example.edu/item/1","reason":"HTTPStatusError:403"}]}}
    picked=choose_papers(papers,rows,old,"measure-v2","study-v2",max_papers=10,current=now)
    assert [x["entry"]["paper_id"] for x in picked]==["new","old-new","upgrade"]
    assert [x["reason"] for x in picked]==["new","new","parser_upgrade"]


def test_no_fulltext_for_metadata_without_open_sources():
    p={"paper_id":"only-metadata","publication_year":2026}
    assert choose_papers({p["paper_id"]:p},[{"paper_id":p["paper_id"],"oa_locations":[]}],
                         {},"m","s")==[]


def test_daily_targets_missing_dois_with_no_cursor(tmp_path,monkeypatch):
    data=tmp_path/"data";data.mkdir();(data/"ontology.yaml").write_text(json.dumps({"nodes":[]}))
    cache=tmp_path/"cache";calls=[]
    rows=[
      {"paper_id":"doi:10.1002/smj.12","doi":"10.1002/smj.12","title":"First paper","publication_year":2026,"authors":["A. Author"]},
      {"paper_id":"doi:10.1002/smj.13","doi":"10.1002/smj.13","title":"Second paper","publication_year":2025,"authors":["A. Author"]}]
    enriched=[{"paper_id":rows[1]["paper_id"]}]
    def reader(name):
        return {"papers.jsonl":rows,"enrichment.jsonl":enriched}.get(name,[])
    class Response:
        def json(self):
            return {"results":[{
                "id":"https://openalex.org/W123",
                "doi":"https://doi.org/10.1002/smj.12",
                "primary_location":{"source":{"issn":["1097-0266"]}},
                "locations":[location()],"abstract_inverted_index":{"Strategy":[0]}
            }],"meta":{}}
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def get(self,url,params):
            calls.append(dict(params))
            return Response()
    monkeypatch.setattr(enrich,"DATA",data)
    monkeypatch.setattr(enrich,"CACHE",cache)
    monkeypatch.setattr(enrich,"read",reader)
    monkeypatch.setattr(enrich.httpx,"Client",Client)
    monkeypatch.setattr(enrich.time,"sleep",lambda v:None)
    status=enrich.harvest(max_pages=3,priority_new=True)
    assert status["matched"]==1 and status["status"]=="complete"
    assert len(calls)==1
    assert "https://doi.org/10.1002/smj.12" in calls[0]["filter"]
    assert "10.1002/smj.13" not in calls[0]["filter"]
    assert "cursor" not in calls[0]
    assert not (data/"staging/openalex_checkpoint.json").exists()


def test_daily_release_dry_run_includes_fulltext():
    from pipeline.release import refresh
    d=refresh("daily",dry_run=True)
    assert d["fulltext_papers"]==4
    assert d["enrichment_requests"]==4
    assert d["paid_api_calls"]==0
