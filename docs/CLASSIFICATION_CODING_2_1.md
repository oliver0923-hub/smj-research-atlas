# 自動分類 v2.1：Domain / Research Topic / Construct / Theory

本分類系統是 **SMJ Research Atlas 編製的工作型 taxonomy**，不是 Strategic Management Journal 的官方分類。12 個實質 Domain 名稱以 Strategic Management Society Interest Groups 作命名參照；額外 Other 節點是資料品質與分類缺口狀態，不是 SMS Interest Group。

## 四個維度與來源證據

1. **Domain**：由已辨識的 Research Topic 或 Construct，按照 Atlas 明列的父節點往上對應；不是期刊官方認證的領域歸屬。
2. **Research Topic**：使用 Crossref 標題的明確詞組，或 OpenAlex 摘要先前產生並保留的 `abstract_phrase_hits` 特徵；標題相似度只給暫定狀態，不當成抽象真值。
3. **Construct**：僅當標題或可查核摘要關鍵詞明確符合六個工作構念的辨識詞組時才標記。**不會**因 Topic 命中就自動推斷使用了某個 Construct，也不把 Construct 直接視為已驗證的 Operational Variable。
4. **Theory**：獨立維度，只在標題／摘要有明確理論詞組時辨識，不由 Domain/Topic/Construct 推論出作者引用或採用某理論。

每篇書目在這四個維度都有至少一個網站可篩選的標籤。未辨識到實質標籤時，依序使用 `OTHER-DOM`、`OTHER-TOP`、`OTHER-CON`、`OTHER-TH`；它們明確表示 **unresolved / insufficient evidence**，而不是主張作者的研究屬於一個真正的「其他」學門。已辨識到實質類別時，不再加入該維度 Other。

## 分類品質與統計分母

每篇 `taxonomy_quality` 有四個維度的 `state`、`substantive_terms`、`fallback_terms`、`best_evidence_grade`、`matching_rules` 與 `score`，前端提供可點選導覽。

| state | 實際意義 |
| --- | --- |
| `abstract_supported` | E1：OpenAlex abstract feature phrase occurrence 或明確編輯層級的繼承 |
| `title_supported` | E0：Crossref title phrase occurrence 或明確編輯層級的繼承 |
| `provisional` | E0：未校準的字詞相似推論 |
| `unresolved_other` | 資訊不足的保底 Other 標記，不計入實質分類涵蓋 |
| `human_approved` | 僅歷史上有真實 reviewer + attestation 的人工紀錄 |

**分數不是正確率，也不是後驗機率。** 來源一致性通過 ≠ 學術概念已獲人工驗證。尚未辨識到 Theory ≠ 文章未使用理論。六個 Construct 以外的概念不能假裝已經納入受控詞彙。

`coverage_report.classification_by_dimension` 提供每個維度之摘要支持、標題支持、暫定、Other、實質分類論文數與分母。主題共現、Theory×Topic、研究機會候選自動排除 Other，避免把未知當成有意義的研究領域。

## 資料更新與版本控制

Ontology 版本 `2.1.0`；完整保留 `data/taxonomy_versions/2.0.0.json`，舊的人工作業（若存在）保留原有稽核證據及拒絕決策。自動分類碼 `atlas-classifier-4.0`。

OpenAlex 完整摘要不重刊於網站；系統只保留 metadata、hash 和對照詞組的特徵。新資料擷取時開始包含 Construct 特徵。既有 v3 抽象關鍵詞紀錄會經後續來源刷新升級為 v4，完成之前較多 Construct 會落在 Other；這是**尚未補齊特徵**，不可稱為抽象實際未提及。

## 主要測試

`python -m pytest tests/test_taxonomy.py tests/test_taxonomy_completeness.py tests/test_v3.py`

也應執行全部 tests、`python -m pipeline.release gate`、`python -m pipeline.cli build`、`npm run build` 及 GitHub Pages 真實部署驗證。若未來要評估分類準確率，需從不同時期／主題建立獨立人工標註的分層樣本，分別計算多標籤 precision、recall、F1；不能用對應詞組驗證代替學術語義準確率。
