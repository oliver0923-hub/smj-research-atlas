"""Create versioned ontology and project documentation; no fabricated paper records."""
import json
from pathlib import Path
root=Path(__file__).parent
domains=[('IND','產業競爭與市場結構','Industry & Competition'),('RES','資源、能力與知識','Resources, Capabilities & Knowledge'),('BEH','組織行為、學習與注意力','Behavioral Strategy & Learning'),('GOV','交易成本、企業邊界與治理','Governance & Firm Boundaries'),('COR','公司策略、多角化與資源配置','Corporate Strategy'),('MNA','併購、撤資與重組','M&A, Divestitures & Restructuring'),('ALL','策略聯盟與網絡','Alliances & Networks'),('INN','創新、技術與知識搜尋','Innovation & Technology'),('INT','國際化、跨國企業與地緣政治','International & Global Strategy'),('LEA','策略領導與公司治理','Strategic Leadership & Governance'),('NMS','非市場、制度、政治與社會策略','Nonmarket & Institutional Strategy'),('ECO','平台、生態系與數位策略','Platforms, Ecosystems & Digital')]
def save(name,text):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
save('data/ontology.yaml',json.dumps([dict(id=c,parent_id=None,label_zh=z,label_en=e,description=z,synonyms=[],version='1.0',status='curated_ontology') for c,z,e in domains],ensure_ascii=False,indent=2))
for f in ['variables.jsonl','relationships.jsonl']:
    if not (root/'data'/f).exists():save('data/'+f,'')
for f in ['seed_papers.yaml','curated_variables.yaml']:save('data/'+f,'[]\n')
save('AGENTS.md','''# SMJ Research Atlas
使用繁體中文。不得捏造文獻或衡量。Crossref metadata 不等於全文審閱。
修改後執行 python -m pytest、python -m pipeline.cli validate、python -m pipeline.cli build、npm run build。
人工欄位不得在 sync 中覆寫。私人全文只能放忽略的本機位置，不得提交或部署。
僅實際人工行為可設定 human_reviewed。不要將 ontology 範例當成逐篇結果。
''')
save('README.md','''# SMJ Research Atlas

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
''')
docs={
'DATA_DICTIONARY':'paper_id = doi: + 正規化 DOI。全文未審閱時 verification_status=metadata_only。Variable 為逐篇紀錄，可含 sample；missingness 為欄位名稱對應 not_reported/not_verified/not_applicable。來源 URL、locator、hash 為衡量驗證前提。完整模型見 pipeline/core.py；尚未實作完整 relationship/ontology schema 約束。',
'METHODOLOGY':'SMJ ISSN 雙來源合併，以 DOI 去重；期刊名稱不符進 quarantine。刊年以 print 優先，其次 online/published。sync 不從 metadata 推論研究理論或方法。保留人工欄位；更新前後差異記入 audit.jsonl。raw staging 僅保留白名單書目欄位，不留摘要／全文。對帳尚未完成，不能聲稱 1980 至今完整收錄。',
'AUTOMATION':'sync-metadata.yml 每日 02:23 UTC（臺北 10:23）與手動觸發，保留跨 run staging artifact。完整成功才建立資料 PR。qa-weekly.yml 每週離線 QA。build-deploy.yml main 更新後部署。validate.yml 驗證 PR。尚未在遠端執行前，排程均只是已寫入設定。',
'REVIEW_GUIDE':'取得合法全文，新增逐篇 variable_id、paper_id、construct、role、proxy 與來源 locator/URL/hash。formula、lag、sample 不清楚時填 null 並標記 missingness。不可由 abstract 自動升為 measurement_verified。LLM 只能提草稿；human_reviewed 需實際人工 reviewer 與日期。PR 應附最短可核查摘述與頁碼，不上傳私人 PDF。執行 validate/build/tests 後人工核對 primary source 再合併。',
'SOURCES':'Crossref https://api.crossref.org/journals/1097-0266/works 與 0143-2095。出版社 https://onlinelibrary.wiley.com/journal/10970266 。Crossref 使用政策 https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/ 。無文章全文授權；不公開全文。OpenAlex 尚未啟用。',
'ROADMAP':'Phase 1：書目、網站、續跑、查核、workflow。待補：完整 schema、瀏覽器互動驗證、工作流遠端執行、Wiley TOC 對帳。Phase 2：合法全文審閱、來源驗證的變數匯入與比較、OpenAlex budgeted enrichment。Phase 3：來源支持的理論關係、研究缺口與網絡。'}
for name,text in docs.items():save('docs/'+name+'.md','# '+name+'\n\n'+text+'\n')
print('Ontology and docs created')
