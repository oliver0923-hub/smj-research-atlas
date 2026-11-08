"""Manual analysis button: bounded workflow, truthful status and no static secrets."""
from pathlib import Path

from pipeline.release import refresh

ROOT=Path(__file__).resolve().parents[1]


def test_manual_batch_has_explicit_budget_and_no_paid_provider():
    plan=refresh("batch",dry_run=True)
    assert plan["status"]=="dry_run"
    assert plan["fulltext_papers"]==60
    assert plan["enrichment_requests"]==12
    assert plan["paid_api_calls"]==0


def test_workflow_accepts_manual_batch_and_keeps_scheduled_daily():
    source=(ROOT/".github/workflows/sync-metadata.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "options: [exhaust_oa, continue_oa, pause_oa, resume_oa, daily, weekly, batch, monthly]" in source
    assert "default: exhaust_oa" in source
    assert 'exhaust_oa|continue_oa|pause_oa|resume_oa)' in source
    assert 'mode="${REQUESTED_MODE:-daily}"' in source


def test_navigation_and_public_launch_controls_are_linked():
    nav=(ROOT/"src/layouts/Layout.astro").read_text(encoding="utf-8")
    home=(ROOT/"src/scripts/research-app.ts").read_text(encoding="utf-8")
    page=(ROOT/"src/pages/run.astro").read_text(encoding="utf-8")
    status=(ROOT/"src/scripts/run-control.ts").read_text(encoding="utf-8")
    assert "['run','啟動論文分析']" in nav
    assert "['run','啟動論文抓取與分析'" in home
    assert "actions/workflows/sync-metadata.yml" in page
    assert 'Run workflow' in page
    assert 'https://api.github.com/repos/' in status
    assert "Authorization" not in status
    assert "GITHUB_TOKEN" not in page


def test_batch_actual_orchestration_uses_bounded_fulltext(monkeypatch,tmp_path):
    from pipeline import release
    import pipeline.enrich as enrich
    called=[]
    monkeypatch.setattr(release,"DATA",tmp_path)
    monkeypatch.setattr(release,"sync",lambda args:called.append("crossref"))
    monkeypatch.setattr(enrich,"harvest",lambda n,priority_new=False:
                        called.append(("enrich",n,priority_new)) or {"status":"complete"})
    import pipeline.crawl as crawl
    monkeypatch.setattr(crawl,"tick",lambda command,max_sources,max_requests,seconds,persist:
                        called.append((command,max_sources,max_requests,seconds)) or {"processed":max_sources})
    monkeypatch.setattr(release,"publisher_check",lambda:{"status":"unavailable"})
    monkeypatch.setattr(release,"gate",lambda:{"status":"passed"})
    monkeypatch.setattr(release,"build",lambda:None)
    monkeypatch.setattr(release,"snapshot",lambda:{"bytes":1})
    result=refresh("batch")
    assert result["status"]=="validated_automatic"
    assert called==["crossref",("enrich",12,False),("enrich",4,True),
                    ("continue_oa",60,180,720)]
