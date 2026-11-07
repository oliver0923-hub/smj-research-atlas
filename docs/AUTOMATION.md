

- 每日 02:23 UTC（臺北 10:23）：Crossref 增量，七日重疊及最近 90 日掃描。
- 每週日 03:47 UTC（臺北 11:47）：有預算的 OpenAlex 補充與 OA 正文擷取。
- 每月一日 04:17 UTC（臺北 12:17）：重算描述性分析與品質報告。
- 每週日 05:11 UTC（臺北 13:11）：額外 coverage QA。
- main 更新：測試、資料驗證與 Astro 建置後部署。

不經人工 PR 核准。資料先通過 schema、DOI／關聯與證據一致性檢查、pytest、套件 audit、正式 build，才將白名單資料壓縮快照寫入 atlas-data 分支並部署。資料分支不能夾帶可執行原始碼；舊版本可由 Git 還原。失敗保留最近成功網站，GHA 日誌及 diagnostics artifact 記錄錯誤。Checkpoint 以白名單還原，禁止任意路徑寫入。



變數、理論與研究機會皆由 GitHub 程序運行：weekly 取得新書目／摘要／合法正文並重新分類及抽取，daily／weekly／monthly 與 main 建置會重算理論導覽、變數字典及 gap_candidates.json。缺少公式、模型角色及機制證據者保留 null；低共現候選不自動升格成已證實學術缺口。預設不執行付費模型。
