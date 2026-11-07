# AUTOMATION

sync-metadata.yml 每日 02:23 UTC（臺北 10:23）與手動觸發，保留跨 run staging artifact。完整成功才建立資料 PR。qa-weekly.yml 每週離線 QA。build-deploy.yml main 更新後部署。validate.yml 驗證 PR。尚未在遠端執行前，排程均只是已寫入設定。
