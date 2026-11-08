"""Published-open-access Wiley PDF candidates.

The presence of a DOI does NOT grant access; only provider OA evidence
authorizes constructing this publisher PDF candidate. The network fetcher
still checks DNS, robots, redirects, response status, identity and license.
"""
import re
from urllib.parse import urlparse

DOI_PATTERN=re.compile(r"^10\.1002/smj\.\d+[a-z0-9-]*$",re.I)
PUBLISHER_HOSTS={"onlinelibrary.wiley.com","sms.onlinelibrary.wiley.com"}


def publisher_oa_status(raw):
    """True only when OpenAlex reports publisher OA, not green-only OA."""
    status=raw.get("open_access") or {}
    if status.get("is_oa") and status.get("oa_status") in {"gold","hybrid"}:
        return True
    locs=list(raw.get("locations") or [])
    for k in ("primary_location","best_oa_location"):
        if raw.get(k):locs.append(raw[k])
    for loc in locs:
        if not loc.get("is_oa"):continue
        if not (loc.get("is_published") or loc.get("version")=="publishedVersion"):continue
        source=loc.get("source") or {}
        publisher_url=loc.get("landing_page_url") or loc.get("pdf_url") or ""
        host=(urlparse(publisher_url).hostname or "").lower()
        source_home=(source.get("homepage_url") or "")
        source_host=(urlparse(source_home).hostname or "").lower()
        if host in PUBLISHER_HOSTS or source_host in PUBLISHER_HOSTS:
            return True
    return False


def wiley_pdfdirect_candidate(doi,raw):
    """Returns a candidate, never a claim of successful lawful downloading."""
    if not isinstance(doi,str) or not DOI_PATTERN.fullmatch(doi):
        return None
    if not publisher_oa_status(raw):
        return None
    return {
        "is_oa":True,
        "is_published":True,
        "is_accepted":False,
        "version":"publishedVersion",
        "pdf_url":"https://sms.onlinelibrary.wiley.com/doi/pdfdirect/"+doi.lower(),
        "landing_page_url":None,
        "license":None,
        "candidate_origin":"OpenAlex publisher-OA indication + deterministic Wiley pdfdirect route; access must be checked",
    }


def merge_wiley_candidate(doi,raw,locations):
    result=list(locations)
    candidate=wiley_pdfdirect_candidate(doi,raw)
    if candidate:
        url=candidate["pdf_url"]
        if not any(loc.get("pdf_url")==url for loc in result):
            result.append(candidate)
    return result
