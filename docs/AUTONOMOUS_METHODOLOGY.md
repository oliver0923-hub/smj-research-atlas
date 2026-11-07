# 自動研究資料系統 v3.0

Atlas 是獨立研究工具，**不是 SMJ 官方 taxonomy**。Domain 仍參照 SMS Interest Groups，Research Topic → Construct → Operational Variable 保持四層關係，Theory 為獨立多重維度。`data/taxonomy_versions/2.0.0.json` 與原始分類來源原封保留。新版本只改變證據、驗證及發布方式，不冒填人工 reviewer。

## 自動發布與三個分離的欄位

| 欄位 | 內容 | 可以支持與不能支持 |
| --- | --- | --- |
| inference_origin | publisher_metadata、crossref_metadata、openalex_metadata、deterministic_rule、model_inference、fulltext_extraction、human_review | 記錄誰／哪種程序產生主張；只有實際人工行為可標 human_review |
| evidence_grade | E0_metadata、E1_abstract、E2_fulltext_section、E3_measurement_text | 描述實際讀到的來源深度；E3 不保證量測效度或因果識別 |
| validation_status | validated_automatic、provisional、failed、insufficient_evidence | 自動檢查來源、欄位與文字一致性；不等於專家同行審閱 |

歷史 review_status 保留相容性，approved／rejected 的實際人工決定有優先權，但不再是正常瀏覽或發布的必要條件。正常排程不會呼叫人工確認命令。分類頁原網址 `taxonomy-review/` 改為「自動分類品質與證據」，不要求擁有者逐篇處理。

分類器先使用可解釋片語及同義詞規則，再以詞彙向量 cosine 產生暫定標記；這是 lexical similarity，**不是已驗證的深層語意理解**。來源、來源 hash、處理版本與時間均可查看。`heuristic_score` 只是規則／相似度分數，沒有 held-out 人工標註集，故不稱機率或正確率。選配模型 adapter 預設停用，無 API key 仍可運作；明確配置模型與每次呼叫預算後，才可使用 `pipeline.inference.infer_labels`，輸出只允許 taxonomy 已有的 ID。它不擷取變數或係數。

## 來源階層與合法取得

1. Crossref：SMJ 雙 ISSN、DOI 正規化、期刊名稱核對；保存線上／印刷日期及可得的更正關聯。
2. OpenAlex：按 DOI 批次補充來源 ID、摘要特徵、引用數及 as-of 日期、外部分類和 OA 位置。外部分類不冒充 SMJ 標記。匿名 cursor 分頁需要 free API key 時，使用有預算的 DOI lookup，不假設付費更新過濾可用。
3. 正文：只嘗試 OA accepted/published 位置，先檢查 robots，再用一般公開 HTTPS 請求；遇到拒絕不繞過。檢查標題與作者一致性，PDF/HTML 解析後記錄原始檔 hash、版本、來源與頁碼。

全文、PDF 與重建摘要只在忽略的 `.cache/` 暫存，不會提交 GitHub 或放進 Pages。公開版不重刊完整摘要，以免將 metadata 授權誤當成原始文字再散布授權。每篇只公開一筆短衡量摘錄（20 詞以內）及獨立撰寫的摘要式定義。OpenAlex 註記 OA 不代表任意重刊權；來源未提供明確 license 時，license 仍為 null，只做公開來源的暫時讀取及短證據定位。

## 逐篇變數如何產生

`deterministic_measurement_span_v1` 只接受正文中明確命名、位於衡量／變數脈絡的 measured／operationalized 等陳述。每篇目前最多取一個可對齊的 named measure，**不是完整變數清單**。名稱、角色與操作化分開：沒有角色文字便維持 unknown；沒有原文公式就保留 null，不把文字定義自行改寫成公式。

E3 紀錄保存 PDF 頁碼（非假定為期刊印刷頁碼）、正規化字元範圍、span hash 與原始檔 hash。`verify_span` 重新取出該段文字、核對 hash 及短摘錄。公式必須與原文一致；sample period、lag、method、data source 或 findings 若無相符的來源文字不能填入。依少數明確文字模式可提供獨立中文摘要與 proxy 描述；未確認的欄位以 null 和 missing_reason 呈現。

目前方法／樣本／係數擷取尚非全面抽取器，尤其不能從標題中的 experiment、performance 或 mediating 推定 RCT、因果效果或中介檢驗。原文版本可能為作者接受稿，網站明列版本。自動通過只表示來源對齊，不等於衡量的理論效度或模型角色已由專家核實。

## 正規化資料與可重現性

`research_graph.json` 提供 paper、claim、theory_tag、topic_tag、construct、operational_variable、variable_alias、measure_evidence、empirical_method、data_source、sample、finding、citation_provenance、extraction_run。未取得證據的表可為空；不填虛構樣本或 findings。相同名稱只做保守正規化，**不自動把語意相近、衡量不同的構念合併**。

`measurement_paths.json` 是 v3 證據導覽的延伸，依同篇論文的自動 Topic 連接實際衡量，不改寫 v2 ontology，也不宣稱 Topic 與 Construct 之間已有理論等價或因果證明。

## 分母、涵蓋率與描述性分析

年度分布以目前索引書目為母體。只排除可明確辨認的社論、索引、更正等通知，其餘文章類型仍可能未完全核實。標記最近刊年為未完整年度。主題比例分母為選定年度／證據條件下的論文數；多重標記不加總成 100%。共現網絡與 Theory × Topic 只是同篇標記共現，不是因果關係。

角色／方法／資料來源只使用有 E3 記錄者，並顯示論文與變數分母；unknown 不當成沒有使用。描述性研究機會只列明確計數規則下的低共現組合，不宣稱新穎性或可發表的研究缺口。

出版社逐期頁面受 HTTP 403 限制，未完成整個出版母體對帳；expected_articles、missing coverage estimate 保持 null。卷期頁顯示的是已索引數量，不是出版社完整產量。

## 排程、品質閘門與失敗隔離

- 每日 02:23 UTC（臺北 10:23）：Crossref 增量，七日重疊及最近 90 日掃描。
- 每週日 03:47 UTC（臺北 11:47）：有預算的 OpenAlex 補充與 OA 正文擷取。
- 每月一日 04:17 UTC（臺北 12:17）：重算描述性分析與品質報告。
- 每週日 05:11 UTC（臺北 13:11）：額外 coverage QA。
- main 更新：測試、資料驗證與 Astro 建置後部署。

不經人工 PR 核准。資料先通過 schema、DOI／關聯與證據一致性檢查、pytest、套件 audit、正式 build，才將白名單資料壓縮快照寫入 atlas-data 分支並部署。資料分支不能夾帶可執行原始碼；舊版本可由 Git 還原。失敗保留最近成功網站，GHA 日誌及 diagnostics artifact 記錄錯誤。Checkpoint 以白名單還原，禁止任意路徑寫入。

## 正式參考文獻與用途

1. Strategic Management Society. (n.d.). *Interest groups & communities*. [官方分類名稱來源](https://www.strategicmanagement.net/connect-participate/interest-groups-communities/).
2. Academy of Management, Strategic Management Division. (n.d.). *Strategic management (STR): Domain statement*. [領域涵蓋範圍](https://www.aom.org/divisions-and-interest-groups/strategic-management/).
3. Nag, R., Hambrick, D. C., & Chen, M.-J. (2007). What is strategic management, really? Inductive derivation of a consensus definition of the field. *Strategic Management Journal, 28*(9), 935–955. [https://doi.org/10.1002/smj.615](https://doi.org/10.1002/smj.615).

Nag et al. 以學者調查與跨領域學者明示定義探討領域共識；本專案只據已核查的出版社摘要作方法啟發，沒有宣稱重現全文方法，也沒有把 Atlas 四層設計歸為作者或 SMJ 的官方分類。歷史 v2 詳細說明仍保存於 repository 的 TAXONOMY_METHODOLOGY.md。


發布後另核對公開 publication manifest 的 source revision、workflow run 與生成時間；平台回報成功卻仍供應舊版本時，工作不算驗收成功。Pages 暫時衝突最多重試兩次，並保留跨工作排他鎖。


## 自動辨識與衍生導覽

週更擷取來源後重新執行 theory／topic 規則與正文量測抽取。每次建置以同一快照生成變數字典、理論導覽、分析及研究機會候選。候選包含主題 A／B 篇數、共同篇數、排除規則、實際支撐 paper IDs、分類版本與 provisional 狀態；新穎性與機制不由低共現推論，維持 null。抽取器版本更新會觸發預算內舊正文再取得，無逐篇人工發布閘門。


每次執行以 source revision + workflow run + attempt 記錄唯一 execution ID；Pages API 使用實際 Git commit。排程資料發布以本次新產生的 atlas-data commit 作 build version，main 更新則使用 main commit，避免每日資料發布共用部署 ID。公開 manifest 分別保留真正的 Git revision、run、attempt 與生成時間。[GitHub Pages REST API](https://docs.github.com/en/rest/pages/pages#create-a-github-pages-deployment) 的 pages_build_version 定義為唯一建置字串。
