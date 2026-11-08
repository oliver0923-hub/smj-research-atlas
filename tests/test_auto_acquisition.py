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
    assert [x["entry"]["paper_id"] for x in picked]==["upgrade","new","old-new"]
    assert [x["reason"] for x in picked]==["parser_upgrade","new","new"]


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
    enriched=[{"paper_id":rows[1]["paper_id"],"abstract_feature_method":"allowed_phrase_occurrence_v7"}]
    def reader(name):
        return {"papers.jsonl":rows,"enrichment.jsonl":enriched}.get(name,[])
    class Response:
        status_code=200
        def raise_for_status(self):pass
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


def test_failed_upgrade_is_throttled_without_dropping_old_receipt():
    now=datetime(2026,11,8,tzinfo=timezone.utc)
    receipt={"accessible":True,"extraction_algorithm_version":"old",
             "study_algorithm_version":"old",
             "last_upgrade_attempt_at":(now-timedelta(days=1)).isoformat()}
    e=entry("p:old")
    assert retry_reason(e,receipt,"measure-new","study-new",current=now) is None
    assert retry_reason(e,receipt,"measure-new","study-new",current=now+timedelta(days=15))=="parser_upgrade"


def test_real_daily_refresh_calls_metadata_and_acquisition(tmp_path,monkeypatch):
    import pipeline.release as release
    import pipeline.enrich as enrichmod
    events=[]
    monkeypatch.setattr(release,"DATA",tmp_path)
    monkeypatch.setattr(release,"read",lambda name:[])
    monkeypatch.setattr(release,"sync",lambda args:events.append("crossref"))
    monkeypatch.setattr(enrichmod,"harvest",
                        lambda pages,priority_new=False:events.append(("openalex",pages,priority_new)) or {"status":"complete"})
    import pipeline.crawl as crawl
    monkeypatch.setattr(crawl,"tick",
                        lambda command,max_sources,max_requests,seconds,persist:events.append(("fulltext",max_sources,seconds)) or {"processed":max_sources})
    monkeypatch.setattr(release,"publisher_check",lambda:{"status":"unavailable"})
    monkeypatch.setattr(release,"gate",lambda:{"status":"passed"})
    monkeypatch.setattr(release,"build",lambda:None)
    monkeypatch.setattr(release,"snapshot",lambda:{"bytes":1})
    result=release.refresh("daily")
    assert result["status"]=="validated_automatic"
    assert events==["crossref",("openalex",4,True),("fulltext",4,150)]


def test_existing_11_fulltexts_are_prioritized_over_large_new_backlog():
    known={f"p:{i}":{"paper_id":f"p:{i}","publication_year":2010+i} for i in range(11)}
    fresh={f"new:{i}":{"paper_id":f"new:{i}","publication_year":2026} for i in range(100)}
    papers={**known,**fresh}
    enrichments=[entry(pid) for pid in papers]
    old={pid:{"accessible":True,"extraction_algorithm_version":"measurement-span-v1",
              "study_algorithm_version":None} for pid in known}
    selected=choose_papers(papers,enrichments,old,"measurement-span-v2-multi",
                           "study-claims-v1",max_papers=4)
    assert len(selected)==4
    assert all(x["reason"]=="parser_upgrade" for x in selected)


def test_upgrades_reuse_proven_oa_url_before_other_candidates():
    papers={"p":{"paper_id":"p","publication_year":2023}}
    receipt={"accessible":True,
             "extraction_algorithm_version":"old","study_algorithm_version":"old",
             "source_url":"https://university.edu/repository/accepted-manuscript.pdf",
             "version":"acceptedVersion","license":None}
    picked=choose_papers(papers,[entry("p")],{"p":receipt},"new-measure","new-study")
    assert picked[0]["reason"]=="parser_upgrade"
    assert picked[0]["sources"][0]["url"]==receipt["source_url"]
    assert len(picked[0]["sources"])>=2
