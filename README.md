# SMJ Research Atlas v3.1

繁體中文、可自動更新的研究資料網站。正式站：https://oliver0923-hub.github.io/smj-research-atlas/

## 執行
```
python -m pip install -e ".[test]"
python -m pipeline.release restore
python -m pipeline.release gate
python -m pipeline.cli build
python -m pytest
npm ci
npm run build
npm run dev
```
Node 22.12+、Python 3.11+；CI Python 3.12。白名單資料由 data/live_state.json.gz 啟動，正常發布以 atlas-data 分支最近通過驗證的快照為準；原 bootstrap 與 taxonomy v2 快照完整保留。

## 網站手動啟動全文抓取

網站側邊導覽的「啟動論文分析」開啟 `/run/`。按鈕會導向 GitHub 的 [Autonomous data release](https://github.com/oliver0923-hub/smj-research-atlas/actions/workflows/sync-metadata.yml) 執行頁。用具備 Actions 執行權限的 GitHub 帳號登入，點選 **Run workflow → batch → Run workflow**。確認後後端自動同步 SMJ 書目、尋找合法 OA 全文、解析變數／假設／實證結果／穩健性檢驗、驗證並部署。**GitHub Pages 是靜態網站，不能直接安全地發出具有寫入權限的 workflow_dispatch；因此 GitHub 的登入與確認不可省略。**網站不保存任何 Personal Access Token。

`batch` 模式每次最多嘗試 60 篇 OA 正文，全文階段預算最多 720 秒。此模式不代表一次抓完所有 SMJ 論文，也無法保證取得付費牆內的正文；沒有證據的欄位仍為 Unknown。網站 `/run/` 會讀取 GitHub 公開工作流程紀錄與最近通過驗證的資料覆蓋率，兩者可能具有時間差。排程更新仍會持續，不需手動操作。

## 更新（無人工審核門檻）
- `python -m pipeline.release refresh --mode daily`：Crossref 新論文 DOI 增量、優先補充新 DOI 的 OpenAlex 資訊，最多嘗試 4 篇 OA 正文（時間預算 150 秒），自動抽取逐篇變數、H/P 假設、結果顯著性、Robustness 與 Sensitivity，通過 QA 後更新網站。
- `python -m pipeline.release refresh --mode weekly`：補充歷史 OpenAlex 資訊及新 DOI，最多嘗試 40 篇 OA 正文（時間預算 600 秒），包含抽取器升級時重新處理既有正文。
- 取得來源：只嘗試 OpenAlex 指向的合法 OA accepted/published 版本；優先嘗試機構典藏 PDF，失敗後可嘗試獨立 landing URL。HTTP 403 或 robots 限制不繞過。失敗來源有 14／60 日冷卻，新 OA 連結出現可提前重試。
- `main` 上的分析程式或同步 workflow 更新也會觸發一輪 daily 處理，並有時間與 GitHub Actions 配額上限。
- `python -m pipeline.release refresh --mode monthly`：重算分析與QA。
- 加 `--dry-run` 只顯示預算、不付費、不發布。
- GitHub Actions → Autonomous data release → Run workflow 選 daily/weekly/monthly。正常排程每日臺北10:23、每週日11:47、每月一日12:17。通過測試、schema、audit、build 才寫資料分支並發布，不需要 PR 核准。

## 來源與資料
Crossref + OpenAlex，完整摘要、PDF 與全文只在忽略的 .cache 暫存；不公開全文。data/variables.jsonl 保留可查核測量資料；data/study_claims.jsonl 保存有原文定位的 Hypothesis、Proposition、Finding、Robustness、Sensitivity 紀錄，公開來源與缺失原因可匯出CSV。來源推論與 evidence_grade、validation_status 分開；不冒填 human_reviewed 或校準正確率。

詳見 [方法與文獻](docs/AUTONOMOUS_METHODOLOGY.md)、[假設、結果與穩健性擷取](docs/STUDY_CLAIMS_METHODOLOGY.md)、[基線稽核](docs/BASELINE_AUDIT.md)、[v3 歷史驗收與限制](docs/ACCEPTANCE_V3.md)。新版會逐篇搜尋多個明確命名的衡量，但不等於完整 IV/DV/Control 清單；公式、角色和顯著性若沒有直接證據必須保留未知。出版社完整目錄受存取限制，coverage_not_audited。Taxonomy 是 Atlas 編製，非 SMJ 官方分類。

## 可還原與人工歷史
Git 保留 v1/v2、原始bootstrap與每個資料分支快照。原有人工核准／拒絕優先；正常排程只做自動來源檢查，不執行 human-attestation。可選人工修正仍以 code review 追蹤，但不是擁有者必須處理的工作。


理論導覽、變數字典與研究機會候選由同一 GitHub 資料快照自動生成。gap_candidates.json 保留規則、分母、支撐 paper IDs、版本與未知的新穎性判定。正文抽取器版本改變後，週更會在預算內重新取得及解析舊來源，不要求逐篇人工審核。部署另以公開 manifest 核對實際上線版本。
