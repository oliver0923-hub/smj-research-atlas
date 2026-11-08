"""Fair, rate-limited OA acquisition planning without human approval.

The queue is deterministic and source-aware. A failure is not evidence of
paywall status; new OA sources can reopen a cooled-down paper immediately.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import ipaddress

BLOCKED_HOSTS={"localhost","localhost.localdomain","metadata.google.internal"}
RETRY_DAYS=14
DENIED_RETRY_DAYS=60


def safe_url(url):
    if not isinstance(url,str) or len(url)>2048:return False
    try:
        p=urlparse(url)
        hostname=(p.hostname or "").lower().rstrip(".")
        if p.scheme!="https" or not hostname or p.username or p.password:return False
        if hostname in BLOCKED_HOSTS or hostname.endswith((".local",".internal")):return False
        if hostname.endswith(".localhost"):return False
        try:
            ip=ipaddress.ip_address(hostname)
        except ValueError:
            return True
        return ip.is_global
    except ValueError:
        return False


def source_candidates(locations,max_urls=8):
    """Try PDF and landing URL separately; skip duplicates and unsafe endpoints."""
    options={}
    for loc in locations or []:
        if not loc.get("is_oa") or not (loc.get("is_accepted") or loc.get("is_published")):
            continue
        for field in ("pdf_url","landing_page_url"):
            url=loc.get(field)
            if not safe_url(url):continue
            host=(urlparse(url).hostname or "").lower()
            # Prefer public repository PDFs to publisher landing pages.
            restricted=any(part in host for part in ("wiley.com","jstor.org","ssrn.com"))
            score=(1 if restricted else 0, 0 if field=="pdf_url" else 1, 0 if loc.get("is_published") else 1)
            item={"url":url,"version":loc.get("version"),"license":loc.get("license"),"kind":field}
            if url not in options or score<options[url][0]:
                options[url]=(score,item)
    return [item for _,item in sorted(options.values(),key=lambda v:(v[0],v[1]["url"]))][:max_urls]


def parsed_datetime(value):
    if not value:return None
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError,TypeError):
        return None


def retry_reason(entry,receipt,measurement_version,study_version,current=None):
    """Return the eligible acquisition reason or None when still cooled down."""
    sources=source_candidates(entry.get("oa_locations"))
    if not sources:return None
    if not receipt:return "new"
    if receipt.get("accessible"):
        if receipt.get("extraction_algorithm_version")!=measurement_version or receipt.get("study_algorithm_version")!=study_version:
            attempted=parsed_datetime(receipt.get("last_upgrade_attempt_at"))
            now=current or datetime.now(timezone.utc)
            if attempted and now-attempted<timedelta(days=RETRY_DAYS):
                return None
            return "parser_upgrade"
        return None
    previous={f.get("url") for f in receipt.get("failures",[]) if f.get("url")}
    # Legacy receipts may not list the URLs they tried. Treat them as
    # temporarily cooled down rather than generating a perpetual new-source
    # retry every day.
    if previous and any(x["url"] not in previous for x in sources):
        return "new_oa_location"
    latest=parsed_datetime(receipt.get("checked_at"))
    if not latest:return "retry_missing_timestamp"
    now=current or datetime.now(timezone.utc)
    if now.tzinfo is None:now=now.replace(tzinfo=timezone.utc)
    rejected=any("403" in (f.get("reason") or "") or "robots_disallowed" in (f.get("reason") or "")
                 for f in receipt.get("failures",[]))
    cooldown=DENIED_RETRY_DAYS if rejected else RETRY_DAYS
    if now-latest>=timedelta(days=cooldown):
        return "retry_after_cooldown"
    return None


def choose_papers(papers,enrichment,receipts,measurement_version,study_version,max_papers=40,current=None):
    """Reparse previously successful texts first, then try new OA manuscripts.

    Reusing proven source locations reduces uncertainty during upgrades.
    New OA candidates follow, with failures cooled down to avoid churn.
    This controls network budget, not scientific representativeness.
    """
    rows=[]
    priority={"parser_upgrade":0,"new":1,"new_oa_location":2,
              "retry_missing_timestamp":3,"retry_after_cooldown":4}
    for e in enrichment:
        p=papers.get(e.get("paper_id"))
        if not p:continue
        reason=retry_reason(e,receipts.get(e["paper_id"]),measurement_version,study_version,current)
        if not reason:continue
        options=source_candidates(e.get("oa_locations"))
        receipt=receipts.get(e["paper_id"]) or {}
        if reason=="parser_upgrade" and receipt.get("accessible"):
            # Reuse the exact previously accessible OA URL first, while still
            # respecting current robots/access checks on every request.
            prior=receipt.get("source_url")
            if safe_url(prior):
                options=[x for x in options if x["url"]!=prior]
                options.insert(0,{"url":prior,"kind":"previously_accessible",
                                  "version":receipt.get("version"),
                                  "license":receipt.get("license")})
        if not options:continue
        year=p.get("publication_year") or 1980
        rows.append((priority[reason],-year,e["paper_id"],e,reason,options))
    rows.sort(key=lambda x:(x[0],x[1],x[2]))
    return [{"entry":r[3],"reason":r[4],"sources":r[5]} for r in rows[:max_papers]]
