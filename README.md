# SMJ Research Atlas

繁體中文 SMJ 書目地圖與逐篇變數查核工具。Astro 靜態網站 + Python Crossref 管線。

## 本機執行
需要 Node 22.12+、Python 3.11+（目前環境為 3.11；CI 使用 3.12）。
```
python -m pip install -e ".[test]"
npm ci
python -m pipeline.cli sync --backfill --max-pages 30 --rows 500
python -m pipeline.cli build
python -m pytest
npm run build
npm run dev
```
若輸出 staged_incomplete，重複相同 sync 命令續跑；尚未完成不會改動已發布書目。跨工作目錄使用模組前請切至本專案。

## 更新
設定 CROSSREF_MAILTO 為研究者聯絡 email。每日增量：`python -m pipeline.cli sync`。增量以最近成功起點減七日查詢 index-date，另掃最近 90 日。首次需先完成 backfill。staging 保留 checkpoint 與去除摘要的來源快照；來源 cursor 若失效，保留舊公開資料，人工清除對應 staging 後重跑。

## 審閱變數與分類
見 docs/REVIEW_GUIDE.md。人工修改透過 PR；自動同步保留 theory/domain/method、verification_status 等 curated 欄位。data/variables.jsonl 是逐篇紀錄；目前為空。缺失欄位用 null，missingness 額外標明原因。新增領域編輯 data/ontology.yaml，遞增 version，再建置。

## 匯出
文獻搜尋頁可匯出篩選結果；完整來源與 provenance 在 data/papers.jsonl，網站 public/data/papers/ 依穩定 hash 分檔。搜尋頁使用較小的索引，詳細頁才取得完整紀錄。

## GitHub Pages
將本目錄作為獨立儲存庫根目錄推送至 main。在 Settings → Pages → Source 選 GitHub Actions，允許 Actions 建 PR。build-deploy 使用儲存庫名稱設定 BASE_PATH，支援 project URL。自訂網域請修改 workflow 的 SITE_URL／BASE_PATH 並加入 CNAME。工作流程預設不自動合併資料 PR。
Actions → SMJ metadata sync → Run workflow 可手動更新；如 backfill 尚未完成，先執行本機全量工作。GitHub 排程可能延遲或因公開 repo 長期無活動停用，需在 Actions 重新啟用。

## 範圍與限制
未與 Wiley 逐期目錄對帳，coverage_not_audited。零已驗證變數不表示論文沒有變數。未啟用 OpenAlex、付費 LLM 或全文下載。理論頁是 ontology 規劃；研究缺口尚無實證。搜尋目前為大小寫不敏感的子字串比對，尚無拼字容錯。瀏覽器互動測試結果需另查驗，Astro build 不等同瀏覽器驗證。

GitHub 初始書目以 data/bootstrap_papers.jsonl.gz 無損壓縮快照保存；read() 在 canonical JSONL 尚不存在時讀取它，後續 sync 產生 papers.jsonl。無全文，內容為此次 Crossref 真實查詢結果。
