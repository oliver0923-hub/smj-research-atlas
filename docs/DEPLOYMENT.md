# 部署與驗證紀錄

2026-11-07：GitHub repo https://github.com/oliver0923-hub/smj-research-atlas
正式站 https://oliver0923-hub.github.io/smj-research-atlas/
歷史私人 Sites（未隨 GitHub Pages 更新，現行版本以正式站為準） https://smj-research-atlas-oliver.oliver0923.chatgpt.site

Crossref 初次全量完成：3,949 筆 DOI，1980–2026，0 隔離，全文與變數皆未審閱。初次同步起點 2026-11-07T13:49:46Z，完成時間見 sync_state。未與 Wiley TOC 對帳，不代表完整涵蓋。
Windows Python 3.11 與 Linux Python 3.12 離線測試通過；Linux npm ci、Astro build、Pages deployment 已成功。正式站 multimarket 搜尋為 6 篇，已檢查 DOI 與詳情頁。尚未進行完整手機／無障礙審核、所有外部 DOI 連結檢查。

目前逐篇分類仍為空；理論入口為 ontology，變數字典與研究缺口為明確空狀態。搜尋尚為子字串比對，未實作 typo-tolerant fuzzy search。完整 variable/relationship schema 與審閱匯入工具仍待擴充。OpenAlex、合法全文擷取與 LLM 未啟用。每日更新產出待審分支／PR，不會自動發布未核准資料。

分類系統自 v2 起採 SMS 參照、四層 DAG 與獨立 Theory，詳見 TAXONOMY_METHODOLOGY.md。原先的空分類狀態屬初始版本紀錄，現行自動候選一律 suggested。
