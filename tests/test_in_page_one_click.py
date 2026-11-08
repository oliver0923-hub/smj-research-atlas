"""The one-click paper button directly fetches OA content; it never opens GitHub."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_paper_button_triggers_real_browser_oa_fetch():
    s=(ROOT/"src/scripts/research-app.ts").read_text(encoding="utf-8")
    assert "import {renderInPageAnalysis} from './in-page-analysis'" in s
    assert "add(onDemand,'button','抓取 OA 全文並分析這篇論文')" in s
    assert "renderInPageAnalysis(onDemandResults,p,abstractPromise)" in s
    assert "on-demand-paper-results" in s
    assert "abstractPromise=showAbstract(app,enriched,p.doi);" in s
    assert "issues/new?title=" not in s
    assert "GitHub 全文擷取任務" not in s

def test_real_oa_pdf_and_html_parsing_contract():
    s=(ROOT/"src/scripts/browser-oa.ts").read_text(encoding="utf-8")
    assert "export async function analyzeBrowserOA" in s
    assert "https://api.openalex.org/works/" in s
    assert "is_oa" in s
    assert "pdfdirect/" in s and "publisherOA(raw)" in s
    assert "pdf.min.mjs" in s and "pdf.worker.min.mjs" in s
    assert "await pdf.getPage(i)" in s
    assert "DOMParser()" in s
    assert "validate(paper,pages)" in s
    assert "article_identity_mismatch" in s
    assert "MAX_BYTES=22_000_000" in s
    assert "MAX_CANDIDATES=8" in s
    for key in ("sample_period","data_source","empirical_method","hypotheses","findings","robustness"):
        assert key in s

def test_results_show_evidence_and_unknowns_without_fake_studies():
    s=(ROOT/"src/scripts/in-page-analysis.ts").read_text(encoding="utf-8")
    assert "import {analyzeBrowserOA,type OAExtract} from './browser-oa'" in s
    assert "await oaPromise" in s
    assert "oa.status==='parsed'" in s
    assert "renderParsedOA(parent,oa,review)" in s
    assert "目前無正文證據可確認 H1、H2 或正式命題" in s
    assert "不代表原文沒有" in s
    assert "頁" in s
    assert "OA 全文直接讀取狀態" in s
    assert "GitHub 全文擷取任務" not in s
    assert "issues/new" not in s

def test_no_browser_secrets_server_posts_or_untrusted_proxy():
    s=(ROOT/"src/scripts/browser-oa.ts").read_text(encoding="utf-8")
    for unsafe in ("localStorage","sessionStorage","Authorization","Bearer ","ghp_",
                   "github_pat_", "api.github.com", "allorigins.win","r.jina.ai",
                   "method:'POST'", "mode:'no-cors'"):
        assert unsafe not in s
    profile=(ROOT/"src/scripts/research-app.ts").read_text(encoding="utf-8")
    assert "GitHub 預填分析任務" not in profile
    assert "需要重新擷取全文？前往 GitHub" not in profile
