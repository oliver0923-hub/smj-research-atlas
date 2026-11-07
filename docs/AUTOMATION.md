# AUTOMATION

sync-metadata.yml 每日 02:23 UTC（臺北 10:23）與手動觸發，保留跨 run staging artifact。完整成功才建立資料 PR。qa-weekly.yml 每週離線 QA。build-deploy.yml main 更新後部署。validate.yml 驗證 PR。尚未在遠端執行前，排程均只是已寫入設定。

2026-11-07 實際遠端增量同步與測試已成功。預設 Actions 禁止建立 PR；PR 步驟失敗時，核對 bot/metadata-update 的 sync_state SHA256 與本次已驗證結果一致才視為成功，否則工作失敗。分支保留供人工比較，不自動合併。
