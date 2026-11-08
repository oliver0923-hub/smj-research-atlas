"""One-shot lawful Wiley OA smoke probe; intentionally no PDF artifact created.

This only checks the one known, publicly declared open-access SMJ article.
For routine crawling every DOI must independently pass OpenAlex publisher-OA
checks; do not copy this test-only permission to unverified DOI candidates.
"""
import json
import time

from .network import OAFetcher, PolicyError

DOI="10.1002/smj.3735"
URL="https://sms.onlinelibrary.wiley.com/doi/pdfdirect/"+DOI


def probe(fetcher=None):
    owned=fetcher is None
    fetcher=fetcher or OAFetcher(interval=1.0)
    fetcher.max_requests=6
    started=time.monotonic()
    result=dict(doi=DOI,url=URL,can_parse=False,source="Wiley open-access smoke fixture")
    try:
        response,chain=fetcher.fetch(URL)
        result["http_status"]=response.status_code
        result["redirect_count"]=len(chain)-1
        result["bytes"]=len(response.content)
        result["pdf_signature"]=response.content.startswith(b"%PDF")
        if response.status_code==200 and result["pdf_signature"]:
            import fitz
            with fitz.open(stream=response.content,filetype="pdf") as doc:
                first=doc[0].get_text("text").lower()
                result["pdf_pages"]=len(doc)
                result["doi_matches"]=DOI in first
                result["open_access_notice"]="open access" in first
                result["can_parse"]=result["doi_matches"] and len(doc)>2
            if result["can_parse"]:
                from .article import digest,parse_article
                from .research import extraction,validate_record
                study={"paper_id":"doi:"+DOI,"doi":DOI,"title":"Corporate development executives and M&A performance"}
                receipt={"source_url":URL,"source_hash":digest(response.content),"accessible":True}
                doc=parse_article(study,response.content,"application/pdf",receipt)
                record=extraction(doc)
                validate_record(record)
                result["analysis"]=dict(
                    text_blocks=len(doc.blocks),pages=result["pdf_pages"],
                    hypotheses=len(record["hypotheses"]),variables=len(record["variables"]),
                    models=len(record["models"]),estimates=len(record["estimates"]),
                    findings=len(record["findings"]),checks=len(record["checks"]),
                    evidence_records=len(record["evidence"]),parser_gaps=len(doc.gaps))
        result["status"]="verified_and_analyzed" if result.get("analysis") else "verified_public_pdf" if result["can_parse"] else "not_verified"
    except PolicyError as exc:
        result["status"]="policy_blocked"
        result["reason"]=str(exc)
    except Exception as exc:
        result["status"]="network_or_parse_failure"
        result["error_class"]=type(exc).__name__
    finally:
        result["elapsed_seconds"]=round(time.monotonic()-started,2)
        if owned:fetcher.close()
    return result


if __name__=="__main__":
    print(json.dumps(probe(),sort_keys=True))
