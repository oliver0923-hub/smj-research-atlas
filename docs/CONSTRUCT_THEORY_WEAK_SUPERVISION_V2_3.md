# SMJ Research Atlas — Theory / Construct 判定增強（v2.3）

## 理論選擇與方法定位

這個版本**不把 Topic Modeling 的群集視為作者採用的 Theory**。主題模型（例如 BERTopic）可發現不同論文群集與遺漏的研究主題，但「同一主題」不表示「同一理論」。對目前沒有人工標註的大型 SMJ 語料庫，採用 **多重詞彙辨識 + contextual multiword weak supervision**，並將「原文／摘要詞彙支持」與「尚未驗證的可能候選」嚴格分開。未使用零樣本模型推論作者引用的理論，也不要求付費 API 或下載大型模型。

可供後續研究的學術起點：
- Yin, Hay, & Roth (2019), *Benchmarking Zero-shot Text Classification: Datasets, Evaluation and Entailment Approach*, EMNLP-IJCNLP, DOI 10.18653/v1/D19-1404。
- Zhang et al. (2023), *Weakly Supervised Multi-Label Classification of Full-Text Scientific Papers*, arXiv:2306.14003。
- Grootendorst (2022), *BERTopic: Neural topic modeling with a class-based TF-IDF procedure*, arXiv:2203.05794。
- Ma et al. (2021), *Issues with Entailment-based Zero-shot Text Classification*, ACL-IJCNLP（提醒零樣本 NLI 仍可能依賴虛假詞彙關聯）。

## 已實作

1. **Ontology v2.3.0**：77 個 Construct、45 個 Theory（皆包含「其他／未判定」）；存檔 `data/taxonomy_versions/2.2.0.json` 保留原版。保留 12 個 SMS Interest Group 領域，沒有任何 SMJ 官方逐篇分類聲明。
2. **明確詞組**：仍使用 `abstract_phrase_hits` 與 `Crossref title` 的確切匹配，來源等級 E1/E0；屬於有詞彙證據的自動標記，但不是經學者人工審核之學術解讀。
3. **新候選層**：`pipeline/semantic.py` 從標題或 OpenAlex 摘要找多詞組的研究語境線索（如 *performance shortfalls*, *patent applications*, *resource based perspective*），產出 `semantic_candidate`；詞組、來源、hash、演算法版本均留痕。**絕不能**將此層作為「作者確實採用該理論」「構念已被操作化」的證據。單一泛用詞（如 innovation、strategy）不會觸發。
4. **分離欄位**：`taxonomy_tags.active` 僅供正式分類；`taxonomy_tags.candidate` 為可能候選。沒有明確標記時，保留 `OTHER-CON` 與 `OTHER-TH`。頁面可以選擇「弱監督候選」查看，單篇頁列出觸發短詞組並明示未經證實。
5. **獨立覆蓋率**：`coverage_report.classification_by_dimension` 新增 `weak_candidate_papers`、`additional_candidate_only_papers`、`potential_coverage_papers`，這三個值**不能與證據支持的 substantive_papers 相加解讀成已確認分類**。
6. **分批回填**：新摘要特徵 `allowed_phrase_occurrence_v6`。既有 OpenAlex 紀錄缺 v6 時，daily 最多使用 20 頁（每頁 40 DOI 的 batch）進行有界補抓；尾聲恢復 4 頁。抓取失敗、沒有可用摘要與違反來源限制時，不捏造分類，也不重刊摘要全文。
7. **方法評估邊界**：現有單元測試核對不能憑空推定理論、候選不能覆蓋正式 Other、明確摘要詞組應優先。但**沒有獨立的人工 gold labels**，故無法宣稱 Precision、Recall、F1 或真正學術語義判定準確率。後續若要導入 BERTopic 或 NLI，先建立分年代／領域的獨立標註並比較錯誤率、候選密度與成本。

## 讀取結果與測試

`python -m pytest tests/test_semantic_weak_supervision.py`

完整驗收仍須 `python -m pytest`、`python -m pipeline.release gate`、`python -m pipeline.cli build`、`npm run build`、正式 GitHub Actions 自動資料更新、公開 Pages 部署驗證，並從成功發布的 `coverage_report.json` 比較實質辨識與候選增量。
