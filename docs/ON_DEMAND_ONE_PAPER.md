# 指定一篇 SMJ 論文的深入解析（On-Demand One-Paper）

## 使用者工作流程

你不必等 3,949 篇 SMJ 書目全部完成 OA 正文解析。現在可以只給一篇 DOI 或接近完全相符的標題，直接要求有限、有來源紀錄的單篇分析。

**ChatGPT 指令範例：**

> 幫我深入分析這篇 SMJ 論文：Value capture theory: A strategic management review。請抓這篇的假設／命題、實證結果與穩健性，以及 sample_period、data_source、empirical_method。

系統會解析為 DOI [10.1002/smj.2592](https://doi.org/10.1002/smj.2592)，並可替 repository owner 建立標題為 `Atlas analyze: 10.1002/smj.2592` 的 GitHub Issue。GitHub Actions `Analyze one SMJ paper on demand` 工作流程將自動針對這一篇 DOI 取用合法 OA 候選並產生報告；結果以 Issue 留言回覆並保存 JSON artifact（30 天）。

也可從 Atlas 單篇論文頁的「啟動這篇論文的單篇深入擷取」連結，建立預先填妥 DOI 的 GitHub Issue；或直接在 GitHub Actions 介面開啟 `workflow_dispatch`，填入 `paper` 標題／DOI。

**實際觸發的安全限制：** Issue 觸發只允許 GitHub repo owner 的新 Issue，且標題必須以 `Atlas analyze:` 開頭；沒有提供任意 URL 參數，僅能搜尋 Atlas 已有的、可唯一辨認的 SMJ DOI。Github Issue 的自然語言內容不會作為 shell 指令執行。AI 訊息本身不會自動觸發，需由連接 GitHub 的對應工具建立該 Issue。

## 檢索與輸出

`pipeline.on_demand` 使用 Atlas 已索引的 DOI/標題，僅限單篇。來源優先重用已經有完整來源驗證的正文記錄；若沒有，就以 OpenAlex 已標記的公開 accepted/published OA 來源為候選，限制最多 8 個來源與 24 個 HTTP 請求，沿用既有 DNS／SSRF、robots、Redirect、429 Backoff、檔案大小與 DOI+題名／作者內容驗證。**不猜測出版社付費 PDF，也不繞過授權。**

報告輸出：

| 分類 | 輸出 |
|---|---|
| 確切 DOI、標題 | 先驗證 Atlas 書目唯一匹配 |
| 論文類型 | Review / Synthesis（有明確題名指標，僅暫定）；否則 unknown |
| `sample_period` | 有原始來源文字對齊 → 值與 evidence；Review 暫定不適用「原創實證樣本」，與文獻回顧涵蓋期間分開；其他 Unknown |
| `data_source` | 有原始來源文字對齊 → 原文記載資料庫；Review 不將被引用研究的資料庫當作者的原創實證數據 |
| `empirical_method` | 有來源對齊 → 原始研究估計方法；Review 的理論／回顧方法獨立，不亂推成 OLS |
| 假設／命題 | 僅輸出正文的 H/P 或來源句型擷取，對齊段落、頁碼與 hash |
| 實證結果與穩健性 | 本篇論文的原創檢驗記錄；不把他人被引述成果當作本篇結果 |
| Theory | 作者明示 E2 / 章節提及／候選，來源對齊，不推定學術有效性 |

若無合法 OA，保留精確狀態 `no_provider_oa_source` 或 `fulltext_not_acquired`，輸出未知與原因，**不能說明該文沒有假設或資料**。Review 類型的「不適用」標記必須與「全文不足，尚待查核」並列。

### 本例的背景

Gans, J., & Ryall, M. D. (2017). *Value capture theory: A strategic management review*. Strategic Management Journal, 38(1), 17–41. https://doi.org/10.1002/smj.2592

這篇文章在摘要與題名清楚說明是 Value Capture Theory 的回顧，主要以 cooperative game theory 作為基礎。它不等同典型有公司樣本、資料庫、回歸模型、H1–Hn 估計的原創實證研究；這些欄位不應一概顯示毫無區別的「未知」。尚未讀取全文時仍保留「暫定」而非絕對排除。

## 維運與限制

- 每次 Issue 對應一次 bounded workflow；已發出的結果可在 Issues 與 JSON artifact 查閱，不直接改寫 Atlas 3,949 篇的正式分類庫，以免單篇工作流與排程更新互相覆蓋。
- 網站只能開啟預填 GitHub Issue，必須有 GitHub 登入且是專案 owner 才能觸發自動分析；不會在 GitHub Pages 靜態站上直接執行伺服器爬蟲。
- GitHub Actions 工作流程有執行期限與權限限制；透過 GitHub 來源站受限的 403 不代表 ChatGPT 或瀏覽器也必定無法查看，也不會繞過。
- 摘要未必揭露所有 Review 文獻納入準則；「原創實證樣本不適用」不能代替系統性回顧研究的 sample window。
- 只發布簡短對齊片段、統計與原文跳轉連結，**不儲存、不重新上傳出版社 PDF**。

## 技術驗證

`python -m pytest tests/test_on_demand.py`

`python -m pipeline.on_demand --query '10.1002/smj.2592' --output-dir data/staging/on_demand`

完整成果以發出 Issue 後 GitHub Actions 的真實 workflow status、實際 OA 存取結果與回覆內容為準。
