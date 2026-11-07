---
layout: ../layouts/Layout.astro
title: 研究分類方法
---

# 研究分類方法：Atlas Taxonomy v2.0.0

**本分類為 SMJ Research Atlas 編製，不是 Strategic Management Journal（SMJ）官方 taxonomy，也未獲 SMS 或 AOM 背書。** 原 v1 十二類僅為初步自訂工作分類，完整封存於 `data/taxonomy_versions/1.0.0.json`，不再作為現行 Level 1。

來源核對日期：2026 年 11 月 7 日。官方網頁可能更新；此日期代表查核快照，不代表組織分類永久不變。中文譯名均由 Atlas 編製。

## 三種來源，各有不同用途

1. **SMS Interest Groups：Level 1 的組織參照。** 保留官方列表上的英文名稱；將其當成網站 Domain 入口，是 Atlas 的編排決定。Research Methods 和 Teaching 是 Communities，並非本次採用的 Interest Groups，故不加入 Level 1。SMS 的會員選組限制不適用於論文標記；論文可有多個 Domain。[1]
2. **AOM Strategic Management Division Domain Statement：範圍檢查。** 以策略決策及其前因／脈絡和結果檢查主題涵蓋，另檢查績效差異、政策、資源、治理、組織間關係與分析層次。對應表是 Atlas 自訂檢查，不是 AOM 對個別分類的認證，也不是已證明窮盡整個領域。[2]
3. **Nag, Hambrick, and Chen（2007）：學術方法參照。** 出版社摘要說明，作者先以學者調查推導隱含的共同領域定義，再以跨領域學者明示的定義作補充。這支持讓研究社群的理解與文本證據相互對照的取徑；不能據此宣稱本文提供了本網站的四層 taxonomy、SMS 分組或變數分類。[3]

本次對 [3] 核查範圍為出版社摘要與書目資訊，未取得完整方法段落；因此不聲稱重現其具體抽樣、詞彙分析或編碼程序，也不提供未核查的頁碼。下述結合演繹與歸納的實作，是 Atlas 的方法設計。

## 四層架構與獨立維度

| 層級 | 定義與用途 | 來源與界線 |
| --- | --- | --- |
| Domain（L1） | 以 SMS Interest Groups 作廣域入口 | 官方英文名稱參照；中文譯名與 L1 編排為 Atlas 自訂 |
| Research Topic（L2） | 描述研究的現象、問題或策略活動 | 自訂工作分類，可跨多個 Domain；不由題目名稱推定理論 |
| Construct（L3） | 區分具有理論意義的抽象概念 | 自訂構念詞彙；詞彙存在不表示任何論文已使用或驗證它 |
| Operational Variable（L4） | 某篇論文對構念的實際衡量 | 必須連到真實 paper_id、variable_id 與來源定位；不放通用猜測公式 |

**Theory 是獨立、多重標記維度，不是第五層，也不置於 Domain 與 Topic 之間。** 同一理論可用於多種主題；同篇論文也可能運用多種理論。Multimarket Contact、M&A、International Strategy 在本版作研究主題，不直接當成理論。

層級關係允許多個 `parent_ids`，形成分層 DAG。它表示研究導覽與概念對應，不是因果關係。例如：競爭策略與合作策略可共同連至多市場接觸主題，再連到市場重疊構念；L4 仍需逐篇證據，不能從此路徑自動產生 overlap 公式。

## 每個分類如何記錄來源

`data/ontology.yaml` 保存來源登錄、節點、層級、版本、方法與範圍檢查；其 JSON 格式也是合法 YAML。每個節點包含 `id`、`level`、`parent_ids`、`origin`、`source_ids`、`method`、`version`、`review_status`、`reviewer`、`reviewed_at`。來源登錄另有 URL、查核日期、可支持的主張與證據定位。

| origin | 意義 | 不可推論的內容 |
| --- | --- | --- |
| official_academic_organization | 來源為官方學術組織的分類名稱；本版限 SMS IG Domain 名稱 | 不代表 SMJ 官方 taxonomy，不代表組織替論文分類 |
| custom_research | Atlas 編製的研究分類、譯名、構念或理論詞彙及對應 | 不能標成組織官方子類，也不表示經全體學者驗證 |
| algorithmic | 標題匹配、上層推導或詞彙成長產生的建議 | 不表示實際理論使用、構念衡量、因果發現或學界共識 |

分類詞彙是否經人工核准，與詞彙來源是否可核對，是不同問題。本版工作節點的 `review_status` 保留 `needs_review`；沒有冒填 reviewer。自動產生的論文分類以 `suggested` 起始。

## 演繹參照、歸納建議與人工裁決

**演繹部分：** 用 SMS 的組織入口建立 L1，以 AOM STR 作範圍檢查，再明列 Atlas 自訂的 L2／L3 與 Theory 詞彙。`scope_check` 記錄自訂對應與來源；方法、地理、產業、分析層次等保留為交叉 facets，避免把分類層次混為一談。

**既有分類的自動建議：** `title_phrase_and_domain_ancestor_v1` 正規化英文標題，對明列的片語作完整詞界匹配；命中 Topic 後，其 Domain ancestors 也只列為建議。Theory 僅在明列的理論片語出現時產生建議。絕不由標題自動指定 Construct、L4、formula 或 `measurement_verified`。False positives 與 false negatives 都可能存在；同義詞規則尚未做人工標註基準的準確率評估。

**新興主題候選：** `title_bigram_document_frequency_v1` 從英文標題找雙詞組，以 corpus 目前最大刊年為終點，近期五年與之前五年比較。以文件數計算，每篇對同詞組最多計一次；近期至少三篇，平滑後普及比例至少 1.5，輸出排名前 20 筆：

`ratio = ((recent_df + 1) / (recent_N + 2)) / ((baseline_df + 1) / (baseline_N + 2))`

候選保留期間、兩期分子與分母、支持論文 ID、方法、來源與版本，不自動指定父節點，也不加入正式 ontology。近期未完整年度、歷史收錄差異、英文分詞及一般性詞組均可能造成偏誤；不能將成長比例解讀為統計顯著、理論新穎性或研究缺口。

## 人工審核與可執行指令

先建置候選：

```sh
python -m pipeline.cli build
```

在 `data/generated/classifications.json` 與 `classification_review_queue.jsonl` 找到 assignment，閱讀來源並查核研究問題、理論與相關段落，再由實際審閱者執行（下列為指令格式，需替換內容）：

```sh
python -m pipeline.cli review-classification \
  --assignment-id '實際 assignment_id' --decision approve \
  --reviewer '實際審閱者' --note '核准理由及研究脈絡' \
  --source-url 'https://合法的原始來源' --evidence-locator '實際章節／頁碼' \
  --human-attestation
```

拒絕時改用 `--decision reject`。程式強制要求人工確認旗標、reviewer、理由、來源、定位；`data/classifications.jsonl` 保存決定，`audit_log` 追加前後狀態、日期、理由與審閱者。**此命令不可放進自動排程，也不能由程式假扮人工審閱。** 技術上旗標是審閱者聲明，不是身分驗證服務；仍以 GitHub 提交與 code review 追蹤責任。

新興詞彙的審核則先判讀支持論文、詞義與時間偏誤，決定拒絕、併入同義詞或提出新 Topic。接受時在 ontology 新增具來源、方法、父節點與 reviewer 的節點，保留 `origin=algorithmic` 及原始候選依據，再經版本更新與 Git review 發布；不要讓建置工作自行核准新節點。

## 多重分類、版本與遷移

- `classifications.jsonl` 是人工決定的權威檔案，與 Crossref metadata sync 分開。自動建議使用穩定 ID；相同 paper／term 的人工接受或拒絕會阻止自動結果覆蓋或重複提出。
- 各 assignment 保存自己的 taxonomy version。新增、拆分、合併或刪改類別須提出版本變更、封存完整快照與遷移說明；不能將舊分類直接標為新版人工確認。
- v1 原始十二類與 paper 的舊代碼保留為 legacy 資料。v2 不自動套用舊代碼；需逐篇重新判讀。舊 Theory 欄位也不直接當成新版已核准理論。
- 驗證會拒絕不存在的來源、版本不一致、Theory 作為階層 parent、錯誤層級關係、無逐篇證據的 L4、無人工審核事件的核准紀錄。
- 本版沒有自動將批准的 Topic 向上升為批准的 Domain；若需兩層都成立，應分別記錄判讀。

每個新版本都應規劃雙人獨立編碼、分歧裁決、跨年份抽樣及 precision／recall 等評估，才能估計分類品質。本次尚未完成這些效度與可靠度評估，不報告虛構的 agreement 或 accuracy。

## 正式參考文獻

1. Strategic Management Society. (n.d.). *Interest groups & communities*. Retrieved November 7, 2026, from https://www.strategicmanagement.net/connect-participate/interest-groups-communities/
2. Academy of Management, Strategic Management Division. (n.d.). *Strategic management (STR): Domain statement*. Retrieved November 7, 2026, from https://www.aom.org/divisions-and-interest-groups/strategic-management/
3. Nag, R., Hambrick, D. C., & Chen, M.-J. (2007). What is strategic management, really? Inductive derivation of a consensus definition of the field. *Strategic Management Journal, 28*(9), 935–955. https://doi.org/10.1002/smj.615

出版社摘要核對頁：https://sms.onlinelibrary.wiley.com/doi/10.1002/smj.615 。[1]、[2] 支持組織名稱與範圍；[3] 支持方法論參照。Atlas 的四層設計、多對多連結、譯名、演算法與審核規則均為本專案設計。
