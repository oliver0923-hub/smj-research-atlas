# 指定一篇 SMJ：直接按鈕取得 Open Access 全文與分析

## 主要操作（網站已提供）

在任何 Atlas 單篇詳細頁按下 **「抓取 OA 全文並分析這篇論文」**。按鈕會在目前的網頁當中執行，不開啟其他 GitHub 表單或 Issue。

1. 讀取本篇的 DOI 與 Atlas 已核對的書目，向 OpenAlex 即時查詢 `is_oa` 和可用 `publishedVersion`／`acceptedVersion` 正文來源。僅在 OpenAlex 確認出版社 OA 時，才加入 Wiley `pdfdirect` 下載候選；不能由 DOI 猜測免費全文。
2. 依序嘗試有限量的 HTTPS PDF／HTML 來源（最多 8 個），遵守瀏覽器的來源限制與 HTTP 回應。PDF 使用固定版本 PDF.js 在瀏覽器暫時解析（最多 65 頁／22MB），HTML 使用 DOMParser 暫時擷取文字。不將 PDF 檔案儲存到 Atlas。
3. 對照 DOI、標題詞彙及作者驗證是同一篇文章，避免錯抓出版社登入頁或其他書目。
4. 本頁直接顯示樣本期間、資料庫／資料來源、實證方法、H1/H2 或 P1/P2、研究結果與 Robustness／Sensitivity，附來源頁碼。每個數值必須有來源文字；正文關鍵詞檢索屬於尚待人工驗證的機器擷取，**不是研究設計、係數及假設支持狀態的正式審核**。
5. 若全部 OA URL 均因 CORS、403、無正文、非本篇或其他因素失敗，顯示來源與錯誤狀態，並保留 OpenAlex 摘要支持的 E1 分析；不得宣稱已完成全文檢索。

### 本次例子：10.1002/smj.3657

Kraft, P. S., Dickler, T. A., & Withers, M. C. (2025). *When do firms benefit from overconfident CEOs? The role of board expertise and power for technological breakthrough innovation*. Strategic Management Journal, 46(2), 381–410. https://doi.org/10.1002/smj.3657

Wiley 頁面標示 **Open Access（CC BY-NC-ND）**，但即便已開放閱讀，出版社也可能沒有提供允許第三方網頁直接讀取的 `Access-Control-Allow-Origin` 標頭。因此，在 GitHub Pages 無專屬後端的情況下，**Open Access 不保證瀏覽器 JavaScript 下載成功**。UI 必須反映實際傳輸及 PDF 解析結果，不可因 Wiley 標記 OA 就顯示「已完成」。

## 未啟用的替代後端（保留在 Repository）

`pipeline/live_api.py` 實作了 DOI 限定、OpenAlex OA 來源核對、既有 Python PDF/HTML 解析器、DNS pinning／robots、請求速率與單次下載上限的來源證據 API，可在具備受管理的後端環境時啟動。現有 Railway 帳戶回覆試用期已結束，沒有完成部署。**前端不會指向尚未存在的 API**，也不會暗藏 GitHub PAT 或把 GitHub workflow 當成匿名公共服務。

## 過去的 GitHub Actions 單篇工作流

`.github/workflows/analyze-one-paper.yml` 與 `pipeline/on_demand.py` 仍保留為 repo owner 的進階／命令列工作流，但 Atlas 論文頁不會再展示其 Issue 建立連結，因為使用者的主要操作已是同頁直接擷取與分析。

## 方法有效性與限制

- 本文的自動 H／P 偵測只是辨認明確標示 `Hypothesis 1` 等句型，不能把摘要推測當成正式假設。
- 估計方法依正文顯性名稱及附近的作者描述辨識；變數在不同模型的角色、統計支持狀態及多種估計規格需人工檢查。
- 適當區分 `not applicable`、`unknown`、`source found but not accessible`、`parsed but not found`。
- 依 Grimmer & Stewart (2013), *Political Analysis*, 21(3), 267–297, https://doi.org/10.1093/pan/mps028，自動文本分類須針對特定研究任務做有效性驗證。

