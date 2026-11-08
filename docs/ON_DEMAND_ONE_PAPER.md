# 一鍵 Open Access 全文分析（Issue #27）

單篇 `/paper/?id=...` 按「抓取 OA 全文並分析這篇論文」即在原頁執行，無須 GitHub Issue、登入、跳頁或工作流提交。按鈕執行期間停用，完成後可重新分析。

## 實際流程

1. 用 DOI 查詢 OpenAlex；核對 Atlas 已索引的書目及 OA／明確授權標記。機構儲存庫即使標為 submittedVersion，也可依明示 CC 授權列為候選；版本原樣揭露，不冒稱出版版本。
2. 優先 POST `{doi}` 到已部署的受限服務 https://smj-oa-gateway-oliver.oliver0923.chatgpt.site/api/document ，服務重新核對 Atlas 書目和 OpenAlex，取得真實 PDF／正文 HTML。前端沒有 GitHub Token 或 API Secret。服務失敗時，有限量嘗試瀏覽器合法直接讀取。
3. 只接受已核准來源主機；IE DSpace 儲存庫透過公開 pid／HAL ORIGINAL bitstream 連結探索，不猜測 PDF 檔名。來源重新導向、robots、授權、DNS、公網位址、檔案型別和大小均有驗證。HTTP 200 的防機器人 HTML 不算全文。
4. 瀏覽器核對回傳 DOI、SHA256 與原文 DOI／標題／作者；PDF.js 4.10.38 解析最多 65 頁／22MB，明示部分解析。HTML 須有實質研究章節。
5. 原頁顯示來源已找到、全文已下載、身分已驗證及原文已解析等獨立狀態；逐欄及逐項保存來源連結、PDF 實際頁序（HTML 為文字段序）、章節線索、最多 24 字詞摘錄、完整標準化句段 hash、位置及 `rule_based_uncalibrated`。
6. 無法取得全文時，明示錯誤原因；既有 Atlas／摘要 E1 資料與當次全文結果分開，不把摘要、快照或 bot challenge 宣稱為成功下載。

## 安全邊界及維運

部署來源位於 `services/oa-gateway/`，有獨立測試、D1 migration 和可重現建置。服務只接受已索引 SMJ DOI，不接受 caller URL、使用者提供的文章或任意代理。允許 GitHub Pages 與本機測試來源，CORS 不是身分驗證，因此另有持久 D1 原子配額：全域 100 次／日、雜湊 IP 12 次／小時、DOI 8 次／小時。每次最多 24 上游請求、6 個來源候選、5 次重新導向、65 秒；同主機間隔至少 1 秒。來源 429 的 Retry-After 跨呼叫保存並遵守，預設暫停一小時。

未儲存全文、分析結果或明碼 IP；PDF 暫時經服務傳輸到瀏覽器記憶體，回應 `no-store`。重新整理後不保留當次結果，也不自動寫入全庫 Atlas 快照。主機 allowlist 需經程式碼審查擴充；不能保證任意 OA 儲存庫皆可存取。服務健康端點 `/api/health`。現有 Railway Python API 保留，但未啟用；公開前端指向真正已部署的上述服務。

## 方法及已知限制

- 所有文字頁均掃描，包括可讀表格文字及附錄；影像公式、複雜表格結構及跨模型語義對應未全面辨識。
- 辨認明確 H1、Hypothesis (H1)、P1 等句型；作者發現句與假設提案、假設支持與統計顯著分開。缺乏明確關聯時支持狀態 Unknown，不推導係數或顯著性。
- `sample_period` 出現不同期間而未可靠對應樣本規格時保留 Unknown／evidence_conflict，並展示各期間證據。資料庫及方法是原文明示詞組，尚非已驗證的主要模型判定。
- Theory 分作者自述使用與僅提及；Construct 只列明示操作化句。詞彙表不是完整理論本體；未命中不代表原文沒有。
- 規則測試通過率不等同獨立學術語義準確率；本次不宣稱全庫品質或已校準 confidence。
- 遵守 403、robots、429、防機器人頁，不處理 CAPTCHA 或繞過授權。OA 授權與可自動下載是不同條件。

## 實際驗證

2026 年 11 月 8 日，`10.1002/smj.3340` 原頁按鈕實際取得 LBS repository acceptedVersion，8,343,034 bytes、35 頁，SHA256 `321701b7bddc6f693e1218aa6c28060a0f1dc13340bc5dd2f2758d13784b1e7f`。辨認 H1、H2、H3a、H3b、H4a、H4b（PDF 8–10 頁）、LBD（12 頁）、USPTO／VentureXpert（13 頁）、DID（11 頁）；衝突樣本期間維持 Unknown。

指定 `10.1002/smj.3657` 找到 Wiley、EconStor 與 IE 合法 OA 線索，但服務實測分別遇到 403、防機器人 HTML 與 429；瀏覽器直連也受 CORS 阻擋。此例**尚未成功解析全文**，不作成功案例。IE 公開 metadata 核對到同 DOI 的 ORIGINAL PDF 連結，仍不以 metadata 或檔案名稱當成已下載。

過去 `.github/workflows/analyze-one-paper.yml` 保留為 owner 進階工具，論文頁沒有其 Issue 連結或教學。

## 方法參考

Grimmer, J., & Stewart, B. M. (2013). Text as data: The promise and pitfalls of automatic content analysis methods for political texts. *Political Analysis, 21*(3), 267–297. https://doi.org/10.1093/pan/mps028 。自動文本方法需依具體任務驗證，不能以程式測試替代研究分類有效性。

DSpace. *REST Contract: Persistent Identifiers*. https://github.com/DSpace/RestContract/blob/main/identifiers.md （IE 公開資料服務的連結探索契約）。
