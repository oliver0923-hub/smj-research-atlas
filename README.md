# SMJ Research Atlas v3

繁體中文、可自動更新的研究資料網站。正式站：https://oliver0923-hub.github.io/smj-research-atlas/

## 執行
```
python -m pip install -e ".[test]"
python -m pipeline.release restore
python -m pipeline.release gate
python -m pipeline.cli build
python -m pytest
npm ci
npm run build
npm run dev
```
Node 22.12+、Python 3.11+；CI Python 3.12。白名單資料由 data/live_state.json.gz 啟動，正常發布以 atlas-data 分支最近通過驗證的快照為準；原 bootstrap 與 taxonomy v2 快照完整保留。

## 更新（無人工審核門檻）
- `python -m pipeline.release refresh --mode daily`：Crossref 增量、QA、分析及快照。
- `python -m pipeline.release refresh --mode weekly`：另補充 OpenAlex、預算40篇 OA 正文嘗試。
- `python -m pipeline.release refresh --mode monthly`：重算分析與QA。
- 加 `--dry-run` 只顯示預算、不付費、不發布。
- GitHub Actions → Autonomous data release → Run workflow 選 daily/weekly/monthly。正常排程每日臺北10:23、每週日11:47、每月一日12:17。通過測試、schema、audit、build 才寫資料分支並發布，不需要 PR 核准。

## 來源與資料
Crossref + OpenAlex，完整摘要、PDF 與全文只在忽略的 .cache 暫存；不公開全文。data/variables.jsonl 保留可查核測量資料，公開來源與缺失原因可匯出CSV。來源推論與 evidence_grade、validation_status 分開；不冒填 human_reviewed 或校準正確率。

詳見 [方法與文獻](docs/AUTONOMOUS_METHODOLOGY.md)、[基線稽核](docs/BASELINE_AUDIT.md)、[實際限制](docs/ACCEPTANCE_V3.md)。目前抽取器每篇最多一筆 named measure，不是完整變數清單。出版社完整目錄受存取限制，coverage_not_audited。Taxonomy 是 Atlas 編製，非 SMJ 官方分類。

## 可還原與人工歷史
Git 保留 v1/v2、原始bootstrap與每個資料分支快照。原有人工核准／拒絕優先；正常排程只做自動來源檢查，不執行 human-attestation。可選人工修正仍以 code review 追蹤，但不是擁有者必須處理的工作。
