"""One-click static-browser study analysis contract.

The browser runs read-only OpenAlex/GitHub searches and renders attributed
evidence. Starting a new authenticated fulltext crawl remains a separate,
explicit owner GitHub issue submission: no access tokens in static JS.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_paper_detail_has_real_button_and_inline_output():
    s=(ROOT/"src/scripts/research-app.ts").read_text(encoding="utf-8")
    assert "import {renderInPageAnalysis} from './in-page-analysis'" in s
    assert "add(onDemand,'button','分析這篇論文（直接在本頁顯示）')" in s
    assert "addEventListener('click'" in s
    assert "renderInPageAnalysis(onDemandResults,p,abstractPromise,issueURL)" in s
    assert "on-demand-paper-results" in s
    assert "abstractPromise=showAbstract(app,enriched,p.doi);" in s


def test_source_evidence_never_implies_nonobserved_results():
    s=(ROOT/"src/scripts/in-page-analysis.ts").read_text(encoding="utf-8")
    assert "export async function renderInPageAnalysis(" in s
    assert "'sample_period','data_source','empirical_method'" in s
    assert "record?.fields?.[k]" in s
    assert "abstractSentences(abstract)" in s
    assert "E1 · 作者摘要陳述；非係數、顯著性或穩健性證據" in s
    assert "摘要的發現句不能當成原文正式假設" in s
    assert "沒有可靠的正文穩健性證據" in s
    assert "目前沒有可對齊的正文紀錄；不代表原文不存在" in s
    assert "暫定不適用於原創實證估計" in s
    assert "sourceUrl" in s


def test_no_client_side_authentication_secret_or_anonymous_github_write():
    s=(ROOT/"src/scripts/in-page-analysis.ts").read_text(encoding="utf-8")
    assert "https://api.github.com" in s
    assert "api+'/search/issues" in s
    assert "api+'/repos/'+REPO+'/issues/'" in s
    for unsafe in ("localStorage","sessionStorage","Authorization:","Bearer ",
                   "ghp_","github_pat_", "fetch(api+'/repos/'+REPO+'/issues',{method:'POST')"):
        assert unsafe not in s
    profile=(ROOT/"src/scripts/research-app.ts").read_text(encoding="utf-8")
    assert "GitHub 預填分析任務（須提交）" in profile
    assert "靜態網站不會要求或保存任何個人 GitHub Token" in profile


def test_existing_automated_issue_result_is_linked_not_faked():
    s=(ROOT/"src/scripts/in-page-analysis.ts").read_text(encoding="utf-8")
    assert "Atlas analyze: " in s
    assert "x.user?.login==='oliver0923-hub'" in s
    assert "x.user?.login==='github-actions[bot]'" in s
    assert "no_provider_oa_source" in s
    assert "查看完整 GitHub 分析報告與來源紀錄" in s
