"""Analyze ONE requested SMJ paper, on demand, with source-aware abstention.

This does not claim to bypass Wiley, scrape subscription content, or infer
results from references. A GitHub issue initiated by the repository owner
triggers a bounded analysis and gets a durable, human-readable outcome.
The paper corpus remains unchanged; output is an issue report + artifact.
"""
import argparse
import difflib
import json
import os
import re
from pathlib import Path

from .article import digest,parse_article
from .cli import DATA,read
from .core import now
from .crawl import locations, active_records
from .network import OAFetcher,PolicyError
from .research import extraction,validate_record
from .selection import safe_url
from .taxonomy import text_key

DOI_RE=re.compile(r"(10\.\d{4,9}/[A-Za-z0-9._;()/:+-]+)",re.I)
ISSUE_PREFIX="Atlas analyze:"
MAX_SOURCES=8
# "Review" is a provisional article-type indication, not proof of the absence
# of empirical material, secondary datasets, hypotheses, or synthesis methods.
REVIEW_WORDS=re.compile(r"\b(?:systematic\s+review|literature\s+review|"
    r"strategic\s+management\s+review|review\s+of\s+(?:the|existing)|"
    r"meta[- ]analysis|bibliometric\s+review)\b",re.I)


def doi_from(value):
    v=(value or "").strip()
    m=DOI_RE.search(v)
    return m.group(1).rstrip(").,;]").lower() if m else None


def resolve(papers,query):
    """Exact DOI first, exact title next, very-high-confidence title match.
    Fail closed on ambiguous queries and never invent new DOI identities.
    """
    q=query.strip()
    if len(q)>500 or not q:raise ValueError("empty_or_oversized_query")
    doi=doi_from(q)
    if doi:
        rows=[p for p in papers if p["doi"].lower()==doi]
        if len(rows)!=1:raise ValueError("doi_not_uniquely_indexed:"+doi)
        return rows[0]
    title=text_key(q)
    rows=[p for p in papers if text_key(p["title"])==title]
    if len(rows)==1:return rows[0]
    if len(rows)>1:raise ValueError("ambiguous_title")
    ranked=sorted(((difflib.SequenceMatcher(None,title,text_key(p["title"])).ratio(),p)
                   for p in papers),key=lambda x:x[0],reverse=True)
    if not ranked or ranked[0][0]<.93 or (len(ranked)>1 and ranked[0][0]-ranked[1][0]<.08):
        raise ValueError("title_not_uniquely_matched; use a DOI")
    return ranked[0][1]


def issue_query(event):
    """Never use untrusted issue content as a shell or arbitrary network URL."""
    issue=event.get("issue") or {}
    title=issue.get("title","")
    if not title.startswith(ISSUE_PREFIX):raise ValueError("not_an_atlas_analysis_issue")
    tail=title[len(ISSUE_PREFIX):].strip()
    body=issue.get("body") or ""
    if len(body)>8000:raise ValueError("oversized_issue_body")
    # Prefer a specific DOI if supplied; other Markdown is not instructions.
    m=re.search(r"(?im)^\s*(?:DOI|Paper DOI)\s*:\s*(.+?)\s*$",body)
    return (doi_from(m.group(1)) if m else None) or tail


def article_type(paper):
    is_review=bool(REVIEW_WORDS.search(paper["title"]))
    return dict(type="review_or_synthesis" if is_review else "empirical_or_conceptual_unresolved",
                evidence="indexed_title_phrase" if is_review else "not_classified",
                status="provisional" if is_review else "unknown",
                caveat="Title-level article type only; full text may reveal original empirical analyses.")


def field_status(field,review,type_field):
    if field and field.get("value") is not None:
        return dict(status="source_grounded",value=field["value"],
                    evidence_ids=field.get("evidence_ids",[]),reason=None)
    if review and type_field in {"sample_period","data_source","empirical_method"}:
        return dict(status="review_type_not_applicable_provisional",value=None,
                    reason="No original empirical sample/data/estimation assumed from review title; "
                           "literature coverage and review methodology still require source check.",
                    evidence_ids=[])
    return dict(status="unknown",value=None,
                reason=(field or {}).get("reason","fulltext_not_accessible"),
                evidence_ids=[])


def _safe_evidence(record,evidence_ids):
    by_id={v["evidence_id"]:v for v in record.get("evidence",[])}
    return [dict(page=v.get("page"),section=v.get("section"),source_url=v["source_url"],
                 block_id=v["block_id"],start=v["start"],end=v["end"],
                 quoted_excerpt=v.get("quoted_excerpt",""),
                 span_hash=v["span_hash"])
            for id in evidence_ids[:3] if (v:=by_id.get(id))]


def concise_rows(record,field):
    out=[]
    for row in record.get(field,[])[:24]:
        ids=row.get("evidence_ids",[])
        out.append(dict(label=row.get("label") or row.get("hypothesis_label")
                        or row.get("kind") or row.get("hypothesis_id"),
                        kind=row.get("kind") or field,
                        summary=row.get("summary") or row.get("test_summary"),
                        reported_support=row.get("reported_support"),
                        significance=row.get("significance"),
                        result=row.get("result"),
                        evidence=_safe_evidence(record,ids)))
    return out


def analyze_one(query,fetcher=None):
    papers=read("papers.jsonl")
    paper=resolve(papers,query)
    meta=article_type(paper)
    eid=paper["paper_id"]
    existing=active_records(read("research_records.jsonl"),read("crawl_queue.jsonl"))
    previous=next((r for r in existing if r["paper_id"]==eid),None)
    # Cache may have been produced by an older extractor; re-fetch if
    # possible to enrich, but never discard a verified previous record.
    record=previous
    attempts=[]
    enrich=next((e for e in read("enrichment.jsonl") if e["paper_id"]==eid),{})
    old_receipt=next((r for r in read("content_receipts.jsonl") if r["paper_id"]==eid),None)
    candidates=locations(enrich,old_receipt)
    need_new=not previous or not previous.get("theory_evidence")
    owned=fetcher is None
    fetcher=fetcher or OAFetcher(interval=1.0)
    fetcher.max_requests=MAX_SOURCES*3
    ontology=json.loads((DATA/"ontology.yaml").read_text(encoding="utf-8"))
    if need_new:
        try:
            for candidate in candidates[:MAX_SOURCES]:
                url=candidate["url"]
                if not safe_url(url):
                    attempts.append(dict(url=url,status="disallowed_source_url"));continue
                try:
                    response,redirects=fetcher.fetch(url)
                    status=response.status_code
                    if status!=200:
                        attempts.append(dict(url=url,status="http_"+str(status)))
                        if status==429:break
                        continue
                    content_type=response.headers.get("content-type","")
                    if not response.content.startswith(b"%PDF") and "html" not in content_type:
                        attempts.append(dict(url=url,status="not_pdf_or_html_article"));continue
                    receipt=dict(source_url=str(response.url),source_hash=digest(response.content),accessible=True)
                    doc=parse_article(paper,response.content,content_type,receipt)
                    candidate_record=extraction(doc,ontology)
                    validate_record(candidate_record)
                    if record is None or len(candidate_record.get("evidence",[]))>=len(record.get("evidence",[])):
                        record=candidate_record
                    attempts.append(dict(url=url,status="parsed",resolved_url=str(response.url),
                                         blocks=len(doc.blocks),redirects=len(redirects)-1))
                    break
                except PolicyError as exc:
                    attempts.append(dict(url=url,status=str(exc)))
                    if str(exc) in ("global_request_budget","host_retry_after"):break
                except (ValueError,KeyError,RuntimeError) as exc:
                    attempts.append(dict(url=url,status=type(exc).__name__,
                                         error=str(exc)[:110]))
                except Exception as exc:
                    attempts.append(dict(url=url,status="network_or_parser_failure",
                                         error_type=type(exc).__name__))
        finally:
            if owned:fetcher.close()
    elif owned:
        fetcher.close()
    fields=record.get("fields",{}) if record else {}
    is_review=meta["type"]=="review_or_synthesis"
    result=dict(
        schema_version="on-demand-paper-1.0",generated_at=now(),
        paper_id=eid,doi=paper["doi"],title=paper["title"],
        paper_type=meta,
        acquisition_status=("source_extracted" if record and any(a["status"]=="parsed" for a in attempts)
                            else "existing_validated_fulltext" if record else
                            "no_provider_oa_source" if not candidates else "fulltext_not_acquired"),
        source_url=record.get("source_url") if record else None,
        source_hash=record.get("source_hash") if record else None,
        candidates_considered=len(candidates),attempts=attempts,
        fields={k:field_status(fields.get(k),is_review,k)
                for k in ("sample_period","data_source","empirical_method")},
        hypotheses=concise_rows(record,"hypotheses") if record else [],
        findings=concise_rows(record,"findings") if record else [],
        robustness=[x for x in concise_rows(record,"checks") if x["kind"] in ("robustness","sensitivity")] if record else [],
        theory_evidence=[dict(term_id=x["term_id"],status=x["status"],
                   source_url=x["source_url"],section=x.get("section"),page=x.get("page"),
                   evidence=_safe_evidence(record,x["evidence_ids"]))
               for x in record.get("theory_evidence",[])] if record else [],
        evidence_state=("source_located_not_semantically_certified" if record else "insufficient_fulltext"),
        limitations=["No full text means no claim about presence or absence of hypotheses or results",
          "For reviews, original empirical sample/method fields may be inapplicable; bibliographic review scope is different",
          "References to other researchers' empirical findings must not be treated as results of this article",
          "Word-level PDF parser is fallible; evidence presence does not establish academic correctness"])
    return result


def markdown(result):
    def safe(v):return str(v or "").replace("|","/").replace("\n"," ")[:300]
    title=result["title"]
    lines=["## 單篇 SMJ 研究資料擷取結果",f"**{safe(title)}**",
           f"DOI: [{result['doi']}](https://doi.org/{result['doi']})",
           f"**執行狀態：** `{result['acquisition_status']}`",
           f"**論文類型：** `{result['paper_type']['type']}`（標題支持、暫定）","",
           "### 研究欄位","| 欄位 | 值／狀態 |","|---|---|"]
    for key,val in result["fields"].items():
        content=safe(val["value"]) if val["value"] is not None else {
            "review_type_not_applicable_provisional":"暫定不適用（原創實證樣本／估計）；仍須檢查回顧方法",
            "unknown":"未知／無來源證據",
        }.get(val["status"],val["status"])
        lines.append(f"| `{key}` | {content} |")
    lines += ["","### 假設／命題、實證結果與穩健性"]
    for key,title in (("hypotheses","假設／命題"),("findings","本篇檢驗結果"),
                      ("robustness","穩健性／敏感度")):
        rows=result[key];lines.append(f"**{title}：** {len(rows)} 筆有來源對齊的擷取紀錄")
        for entry in rows[:8]:
            label=safe(entry.get("label") or entry.get("kind"))
            citations=entry.get("evidence") or []
            loc=(f"{safe(citations[0].get('section'))} / page {citations[0].get('page')}"
                 if citations else "source locator unavailable")
            lines.append(f"- {label}: {safe(entry.get('summary') or entry.get('reported_support') or entry.get('result'))} ({loc})")
    if not result["source_url"]:
        lines+=["","**正文尚未合法取得：** 以上沒有擷取紀錄不代表原文不存在這些內容。"]
    else:
        lines+=["",f"已使用的來源：{result['source_url']}"]
    lines+=["",f"合法 OA 候選：{result['candidates_considered']}；本次嘗試：{len(result['attempts'])}。"]
    if result["attempts"]:
        lines+=["","### 本次來源存取嘗試（便於檢查 403／robots／解析限制）"]
        for attempt in result["attempts"][:MAX_SOURCES]:
            lines.append(f"- `{safe(attempt['status'])}`：{safe(attempt['url'])}")
    lines+=["","擷取記錄與頁碼會保留於本次 GitHub Actions 的 JSON artifact；沒有公開儲存 PDF。",
           "來源文字對齊不等於學術語義正確率或人工驗證。"]
    return "\n".join(lines)+"\n"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--query",default=None)
    p.add_argument("--github-event",type=Path)
    p.add_argument("--output-dir",type=Path,default=Path("data/staging/on_demand"))
    a=p.parse_args()
    event=json.loads(a.github_event.read_text()) if a.github_event else {}
    query=a.query or issue_query(event)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    try:
        result=analyze_one(query)
    except ValueError as exc:
        result=dict(schema_version="on-demand-paper-1.0",query=query,
                    acquisition_status="cannot_identify_exact_indexed_paper",
                    reason=str(exc)[:250],generated_at=now())
        summary="無法唯一辨認這篇 Atlas 論文；請提供精確 DOI。\n\n"+result["reason"]
    else:
        summary=markdown(result)
    (a.output_dir/"analysis.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.output_dir/"result.md").write_text(summary,encoding="utf-8")
    print(json.dumps({k:result.get(k) for k in
                      ("doi","acquisition_status","candidates_considered","attempts","generated_at")},
                     ensure_ascii=False))


if __name__=="__main__":main()
