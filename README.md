# SMJ Research Atlas v4

繁體中文、可自動更新的研究資料網站。正式站：https://oliver0923-hub.github.io/smj-research-atlas/

v4 全庫 OA 來源循環、跨工作 checkpoint、逐欄證據、37 個獨立來源評估 query 與技術限制，見 [EXHAUSTIVE_OA_V4.md](docs/EXHAUSTIVE_OA_V4.md)。執行頁顯示完整遍歷分母、Unknown 原因與公開 precision/recall；來源對齊不是語義正確率。自動資料不是人工已審，也不是 SMJ 官方分類。

## 執行
```
python -m pip install -e ".[test]"
python -m pipeline.release restore
git fetch origin atlas-data
python -m pipeline.release restore --from-ref origin/atlas-data
python -m pipeline.release gate
python -m pipeline.cli build
python -m pytest
npm ci
npm run build
npm run dev
```
Node 22.12+、Python 3.11+；CI Python 3.12。白名單資料由 data/live_state.json.gz 啟動，正常發布以 atlas-data 分支最近通過驗證的快照為準；原 bootstrap 與 taxonomy v2 快照完整保留。

## 網站手動啟動全文抓取

網站側邊導覽的「啟動論文分析」開啟 `/run/`。按鈕會導向 GitHub 的 [Autonomous data release](https://github.com/oliver0923-hub/smj-research-atlas/actions/workflows/sync-metadata.yml) 執行頁。用具備 Actions 執行權限的 GitHub 帳號登入，點選 **Run workflow → exhaust_oa → Run workflow**。確認後後端自動同步 SMJ 書目、尋找合法 OA 全文、解析變數／假設／實證結果／穩健性檢驗、驗證並部署。**GitHub Pages 是靜態網站，不能直接安全地發出具有寫入權限的 workflow_dispatch；因此 GitHub 的登入與確認不可省略。**網站不保存任何 Personal Access Token。

主要入口選擇 `exhaust_oa`，沿用全庫來源佇列，每三小時自動 `continue_oa`，每次最多 180 sources／450 requests／600 秒。可選 `pause_oa` 暫停、`resume_oa` 接續。原 `batch` 保留 v3 相容用途。網站 `/run/` 會讀取 GitHub 公開工作流程紀錄、durable 來源進度與最近發布的欄位覆蓋率，三者可能具有時間差。

## 更新（無人工審核門檻）
- `python -m pipeline.release refresh --mode daily`：Crossref 新論文 DOI 增量、優先補充新 DOI 的 OpenAlex 資訊，沿持久佇列最多嘗試 4 個 OA 來源（時間預算 150 秒），自動抽取逐篇變數、H/P 假設、結果顯著性、Robustness 與 Sensitivity，通過 QA 後更新網站。
- `python -m pipeline.release refresh --mode weekly`：補充歷史 OpenAlex 資訊及新 DOI，沿持久佇列最多嘗試 40 個 OA 來源（時間預算 600 秒），包含抽取器升級時重新處理既有正文。
- 取得來源：只嘗試 OpenAlex 指向的合法 OA accepted/published 版本；優先嘗試機構典藏 PDF，失敗後可嘗試獨立 landing URL。HTTP 403 或 robots 限制不繞過。失敗來源有 14／60 日冷卻，新 OA 連結出現可提前重試。
- `main` 上的分析程式或同步 workflow 更新也會觸發一輪 daily 處理，並有時間與 GitHub Actions 配額上限。
- `python -m pipeline.release refresh --mode monthly`：重算分析與QA。
- 加 `--dry-run` 只顯示預算、不付費、不發布。
- GitHub Actions → Autonomous data release → Run workflow 選 daily/weekly/monthly。正常排程每日臺北10:23、每週日11:47、每月一日12:17。通過測試、schema、audit、build 才寫資料分支並發布，不需要 PR 核准。

## 四維研究分類（Taxonomy v2.4）

所有已索引論文都有 Domain、Research Topic、Construct、Theory 的網站標記與逐維度分類品質。來源優先使用 OpenAlex 摘要詞組特徵，並使用 Crossref 標題補充；未能辨識時顯示「其他／未判定」，**不當成有效學術分類或缺乏相關研究的證據**。新 Abstract Construct 特徵會透過既有每日 OpenAlex 刷新分批補齊。Domain 的 12 個實質名稱參照 SMS，Other 是 Atlas 自訂缺失狀態；Theory 不由 Topic 猜測。

詳見 [分類編碼與資料品質 v2.1](docs/CLASSIFICATION_CODING_2_1.md)，以及 [v2.3 Construct／Theory 多標籤弱監督判定與候選](docs/CONSTRUCT_THEORY_WEAK_SUPERVISION_V2_3.md)。 最新 [v2.4 未分類論文摘要稽核：556 篇、39 個新 Construct、5 個特定 Theory／Framework](docs/ABSTRACT_COVERAGE_GAP_AUDIT_V24.md) 明列 DOI、可重現抽樣、分類缺口與方法限制。v2.4 有 116 個 Construct、50 個 Theory（各含其他）；新增摘要脈絡短語產生的「候選分類」，與真正有詞彙證據的正式分類獨立。候選不代表作者確實引用理論或測量該構念；分類品質頁面分開顯示兩種覆蓋率。更新後每日有界回填舊摘要特徵，並保留 v2.2 ontology 歷史快照。
### Wiley 已確認 OA 的原版 PDF

`pipeline/wiley.py` 會針對經 OpenAlex 明確標記出版社 Open Access 的 `10.1002/smj.*` 論文，額外加入 `https://sms.onlinelibrary.wiley.com/doi/pdfdirect/<DOI>` 作為有界抓取候選。仍必須通過 robots、403、來源身份與 PDF 解析，不會以 DOI 本身認定所有原版 PDF 可公開下載。以 `10.1002/smj.3735` 為實際 OA 煙霧測試範例：`python -m pipeline.wiley_probe`，只印出下載／解析與變數／假設記錄數，不儲存或公開 PDF。詳見 [擴充與來源方法](docs/TAXONOMY_ABSTRACT_WILEY_V2_2.md)。


## 單篇論文直接擷取合法 OA 全文

Atlas 每篇 `/paper/?id=...` 詳細頁提供 **「抓取 OA 全文並分析這篇論文」** 按鈕。按一下即查詢 OpenAlex，經已部署的 DOI 限定 OA 取件服務下載 PDF／HTML，在瀏覽器 PDF.js 4.10.38 驗證書目及解析原文，直接顯示研究欄位、假設、發現、穩健性、Theory／Construct 與逐項原文頁碼、短摘錄、hash 及未校準可信程度。無須 GitHub Issue、登入或跳轉；Atlas 快照與當次分析分開。

**實際邊界：** 取件服務克服一般 CORS，遵守授權、robots、403、429 與防機器人回應，有 D1 持久配額與 Retry-After。`smj.3340` 已實際下載 8.34MB／35 頁並在原頁解析；指定 `smj.3657` 目前因來源 403／bot challenge／429 尚未成功。無全文或無可靠語義對應時保留 Unknown，不虛構結果。全文不持久儲存，解析結果僅在本次頁面記憶體。詳見 [單篇 OA 分析與驗證](docs/ON_DEMAND_ONE_PAPER.md) 及 [服務原始碼](services/oa-gateway/)。

## 合法全文的理論證據（v4.1）

針對可依法自動取得的 Open Access 正文，解析 Introduction、Theoretical Background、Literature Review、Hypotheses Development 等段落，將作者明確陳述採用的 Theory 和單純提及的 Theory 分開。所有紀錄保留頁碼、段落 ID、來源 hash 與有上限的引文；作者明示為 E2 Fulltext Theory，自動語意候選與僅提及標籤不會冒充已採用理論。先前成功的 OA 全文會在 extractor 升級後優先重新嘗試，不規避出版商存取限制。詳見 [全文理論來源與章節證據方法](docs/FULLTEXT_THEORY_EVIDENCE_V41.md)。

## 未分類摘要分析

`python -m pipeline.taxonomy_gap_audit --batches 24 --top 90` 使用 OpenAlex API 暫存約 480 篇未定 Construct 與 480 篇未定 Theory 的摘要（去重後依取得狀況變動）並輸出高頻候選詞組、代表 DOI 與分母，不儲存／重刊完整摘要。分類品質頁面將「沒有摘要」「有摘要但尚待最新詞典重建」「已掃描仍未匹配」分別計數。**Topic Modeling 不能自動證明作者使用某理論**，因此未將未驗證的語義群集提升成正式 Theory。

## 來源與資料
Crossref + OpenAlex，完整摘要、PDF 與全文只在忽略的 .cache 暫存；不公開全文。data/variables.jsonl 保留可查核測量資料；data/study_claims.jsonl 保存有原文定位的 Hypothesis、Proposition、Finding、Robustness、Sensitivity 紀錄，公開來源與缺失原因可匯出CSV。來源推論與 evidence_grade、validation_status 分開；不冒填 human_reviewed 或校準正確率。

詳見 [方法與文獻](docs/AUTONOMOUS_METHODOLOGY.md)、[假設、結果與穩健性擷取](docs/STUDY_CLAIMS_METHODOLOGY.md)、[基線稽核](docs/BASELINE_AUDIT.md)、[v3 歷史驗收與限制](docs/ACCEPTANCE_V3.md)。新版會逐篇搜尋多個明確命名的衡量，但不等於完整 IV/DV/Control 清單；公式、角色和顯著性若沒有直接證據必須保留未知。出版社完整目錄受存取限制，coverage_not_audited。Taxonomy 是 Atlas 編製，非 SMJ 官方分類。

## 可還原與人工歷史
Git 保留 v1/v2、原始bootstrap與每個資料分支快照。原有人工核准／拒絕優先；正常排程只做自動來源檢查，不執行 human-attestation。可選人工修正仍以 code review 追蹤，但不是擁有者必須處理的工作。


理論導覽、變數字典與研究機會候選由同一 GitHub 資料快照自動生成。gap_candidates.json 保留規則、分母、支撐 paper IDs、版本與未知的新穎性判定。正文抽取器版本改變後，週更會在預算內重新取得及解析舊來源，不要求逐篇人工審核。部署另以公開 manifest 核對實際上線版本。
