# 全庫 OA 與研究證據 v4

此系統為 SMJ Research Atlas 自訂研究工具，並非 SMJ 官方分類或資料庫。Domain 仍以 SMS Interest Groups 為主要參照，AOM STR Domain Statement 檢查涵蓋範圍；既有四層 taxonomy 與獨立多標記 Theory 不變。分類來源、方法、版本、演算法建議與人工審核能力維持既有 taxonomy schema；無人工審核時不得標成人工已審。

## 範圍與完成條件

每個已索引 DOI 都有一筆 crawl_queue；OpenAlex 的 accepted/published OA locations、歷史合法成功來源及 OA 書目頁直接連結的 PDF 各有獨立 source ledger。未限制前八個 URL。這是有界的來源搜尋，不能解讀為搜尋完網際網路，或認定沒有 OA 的論文永久無法取得。

一輪完成必須同時滿足：所有 DOI 有 provider discovery receipt，且此輪每個候選 URL 都有實際嘗試或明確政策阻擋理由。403、429、robots、404、DNS/SSRF、身分不符、摘要頁和解析失敗分開記錄；403 不等同付費牆。完成不表示全文全部成功，亦不表示每個研究欄位完整。

## 循環、恢復與安全

GitHub Actions 每三小時執行 continue_oa，每次至多 180 sources、450 HTTP requests、600 秒。未遍歷候選先於升級與重試；任何一篇有多個來源都不會讓另一篇永久飢餓。網路有 host throttle、robots、Retry-After、檔案大小與重導限制。HTTPS/public-DNS 檢查包含每次重導及實際連線 IP pinning，停用環境代理及驗證資訊轉送。

每個來源後寫本機 atomic JSONL；Actions 每 15 個來源或約 50 秒將通過結構驗證的 snapshot commit 至 atlas-data。最終建站或部署失敗不會倒退已保存的 checkpoint。突然中斷可能重做最後尚未 commit 的至多 15 個來源。不同 host 的網路時間無法保證一樣。

在網站「執行」頁前往 workflow_dispatch，可選 exhaust_oa（開始／繼續）、pause_oa、resume_oa；無瀏覽器 PAT。繼續沿用 cycle_id，restart_oa 僅供 CLI 明確重新遍歷。完成後進入低頻 discovery monitoring；新 DOI/來源立即重開，provider 重查週期 30 天、檢查是否到期每 7 天。升級解析器可重試解析失敗及已成功來源；舊成功資料保留直到新版本通過驗證。

## 解析與獨立證據

ArticleDocument 保存頁、章節、雙欄排序、文字區塊、表格 cell、公式候選、附錄與解析缺口。PDF 使用 PyMuPDF 文字及幾何；HTML 必須同時有研究內容與結果／討論／附錄結構，書目摘要頁不算全文。DOI/標題/作者身分比對後才接受。掃描頁及圖片公式未執行 OCR；外部補充檔僅在已索引合法來源出現時可進入佇列。

32 種 variable fields 與 17 種 paper fields 各保存 value、status、reason、evidence_ids。證據具有 source/block/span/quote hash、起迄 offset、頁、章節、表格 row/column、bbox 與方法／版本。每篇公開原文摘錄合計上限 200 words，其餘保留位置與 hash；私人全文不進 git。hash 對齊是工程完整性，不能當語義準確率。

同名不同定義不強制合併。不同模型數值保留自己的 cell；只有可辨認的關係才連到變數／假設，未辨認 model、DV、SE、p-value 或 legend 的值維持 Unknown。支持假設與統計顯著性分開。負係數不推導支持；有星號不猜 p 門檻；提到 robustness 不代表通過。

文字明示的 normalized-by／divided-by 保存 numerator、denominator 與 inferred_ratio；此比值不是原文公式，formula 仍 Unknown，除非找到原文算式。Known 表示規則擷取有來源，不表示經專家語義審查。

Unknown 理由包括 not_reported、not_found_after_search、not_applicable、inaccessible_fulltext、not_parsed、ambiguous、not_yet_processed、evidence_conflict。現行保守規則不會在文字搜尋失敗後逕稱作者沒有報告；多個不等價期間保留 evidence_conflict。缺乏全文的論文未生成虛構研究紀錄。

## 評估與可重現性

evaluation/gold.json 為 15 篇不同真實 SMJ PDF 的獨立原文標註，排除開發案例 smj.3340。先凍結研究抽取器，再直接檢視原始 PDF 的指定頁，未使用模型輸出製造答案。樣本為可取得來源的 purposive sample（2010–2026），並無第二位盲審專家。只評估具明確標註的 named data sources、empirical methods、primary sample periods，其他欄位準確率 Unknown。

執行 `python -m pipeline.evaluate --manifest .cache/evaluation_manifest.json`，需合法取得相同 SHA256 私人 PDF。公開 gold 包含來源 URL/hash 與 PDF 頁碼，不含全文；結果公開每個 query 的 TP/FP/FN、precision/recall/F1、exact match 與 abstention。Unknown 在正例算漏抓，不當作正確答案。CI 驗證公開評估算式與 manifest，未取得原始 PDF 的 CI 不假裝重跑語義評估。

`python -m pytest`、`python -m pipeline.cli validate`、`python -m pipeline.release gate`、`python -m pipeline.cli build`、`npm run build` 是發行檢查。測試 fixtures 驗證錯誤案例與規格，不等於真實論文準確率。migration baseline 記錄 v3.1 的已知量與 taxonomy hash；v3→v4 增量恢復不刪除舊人工紀錄。

## 已知技術妥協

無付費 LLM／OCR key 依賴；採可重現規則，因此未見過的資料庫別名、定性方法、隱含變數與複雜模型的 recall 有限。文獻回顧與實際使用的識別仍可能誤判，公開評估會計入 false positives。表格無框線、跨頁合併與公式影像常無法可靠復原，保留缺口。研究缺口與新興主題仍是演算法建議，不能聲稱為已證實理論缺口。

正式網站與 raw atlas-data 的進度可能有部署時間差；執行頁優先讀取 durable progress JSON，並保留網站 fallback。

所有 daily/weekly/batch 相容入口也使用同一 v4 佇列並尊重 pause；不會由舊取得器繞過暫停。完成狀態仍會在任何到期失敗重試或 parser/extractor 升級時重開，不必等待 provider 重查。

## 補充關係評估與真實來源迴歸

`python -m pipeline.evaluate_relationships` 在相同 15 篇來源中的 3 篇，另以原始 PDF 指定頁標註 26 個關係 query；此補充標註在初始三欄評估之後建立，抽取器維持凍結、未依答案調參。假設支持：TP=4、FN=2、precision=100%、recall=66.7%；指定的顯著性（3）、角色（4）、假設—變數—模型連結（6）、模型估計（3）、p-value（3）、穩健性結果（1）均全部棄答／漏抓，不能宣稱關係辨識已可靠。precision 分母為零時為 Unknown，不能報成 100%。網站公開兩組評估，未評估的欄位仍 Unknown。

smj.3340 的來源 URL、SHA256、PDF 第 12 頁與短摘錄保存於 evaluation/smj3340_regression.json，CI 從已驗證 atlas-data 恢復實際抽取紀錄，核對 numerator/denominator、state-year、inferred_ratio 與未知原文 formula。這是開發來源迴歸，沒有混入獨立評估樣本。PR CI 也恢復真實快照後執行此檢查。
