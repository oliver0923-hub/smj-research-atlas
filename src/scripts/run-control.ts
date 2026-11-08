// Public, read-only status monitor. Never embeds a GitHub token in GitHub Pages.
const GITHUB_REPO='oliver0923-hub/smj-research-atlas';
const GH_ORIGIN='https://github.com/'+GITHUB_REPO+'/actions/runs/';
const API='https://api.github.com/repos/'+GITHUB_REPO+'/actions/workflows/sync-metadata.yml/runs?per_page=5';
const base=import.meta.env.BASE_URL;

const add=(parent:Element,kind:string,content:string,cls?:string)=>{
  const el=document.createElement(kind);
  el.textContent=content;
  if(cls)el.className=cls;
  parent.appendChild(el);
  return el;
};

async function loadMetrics(){
  const note=document.querySelector('#analysis-summary');
  const target=document.querySelector('#run-metrics');
  if(!note||!target)return;
  try{
    const response=await fetch(base+'data/coverage_report.json',{cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const record=await response.json();
    const metrics=[
      ['SMJ 文獻書目',record.papers],
      ['已成功解析正文',record.accessible_fulltexts],
      ['有來源證據的變數',record.measurement_text_aligned],
      ['已定位的研究假設',record.hypothesis_records],
      ['已定位的實證結果',record.finding_records],
      ['穩健性相關文字',record.robustness_records],
      ['敏感性相關文字',record.sensitivity_records]
    ] as const;
    target.replaceChildren();
    for(const [label,value] of metrics){
      const card=add(target,'article','','card');
      add(card,'div',label,'muted');
      add(card,'div',value===null||value===undefined?'未知':Number(value).toLocaleString('zh-TW'),'metric');
    }
    note.textContent='資料快照產生時間：'+(record.generated_at?new Date(record.generated_at).toLocaleString('zh-TW'):'未提供');
  }catch(e){
    note.textContent='目前無法讀取公開資料快照；仍可從 GitHub 啟動抓取與分析。';
  }
}

function renderRuns(rows:any[]){
  const history=document.querySelector('#run-history');
  const note=document.querySelector('#run-status');
  if(!history||!note)return;
  history.replaceChildren();
  if(!rows.length){note.textContent='目前沒有可公開讀取的執行紀錄。';return;}
  const mapping:Record<string,string>={queued:'排隊中',pending:'等待執行',in_progress:'執行中',completed:'已完成',success:'成功',failure:'失敗',cancelled:'取消',timed_out:'逾時',skipped:'跳過'};
  note.textContent='已讀取 '+rows.length+' 筆最近執行紀錄（重新整理頁面更新）。';
  for(const row of rows){
    if(!Number.isSafeInteger(row.id))continue;
    const item=add(history,'article','');
    const href=GH_ORIGIN+row.id;
    const a=add(item,'a','#'+row.id+' · '+(mapping[row.status]||row.status||'未知')) as HTMLAnchorElement;
    a.href=href;a.target='_blank';a.rel='noopener noreferrer';
    add(item,'p',
      '結果：'+(mapping[row.conclusion]||row.conclusion||'尚未完成')+
      ' · 來源：'+(row.event||'未知')+
      ' · 建立時間：'+(row.created_at?new Date(row.created_at).toLocaleString('zh-TW'):'未知'),
      'muted');
  }
}

async function loadRuns(){
  const note=document.querySelector('#run-status');
  if(!note)return;
  try{
    const response=await fetch(API,{headers:{'Accept':'application/vnd.github+json'}});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const payload=await response.json();
    renderRuns(Array.isArray(payload.workflow_runs)?payload.workflow_runs:[]);
  }catch(err){
    note.textContent='GitHub 公開執行紀錄暫時無法取得（可能為 API 限流）；可以直接進入上方 GitHub Actions 查看。';
  }
}
void Promise.all([loadMetrics(),loadRuns()]);


async function loadCrawl(){const target=document.querySelector('#crawl-progress');if(!target)return;try{let response=await fetch('https://raw.githubusercontent.com/'+GITHUB_REPO+'/atlas-data/data/crawl_progress.json',{cache:'no-store'});if(!response.ok)response=await fetch(base+'data/crawl_progress.json',{cache:'no-store'});if(!response.ok)throw Error();const r=await response.json();target.replaceChildren();add(target,'p','狀態：'+r.state+' · 本輪完成：'+(r.round_complete?'是（僅此快照可用來源）':'否')+' · 更新（UTC）：'+r.generated_at,'status-line');const grid=add(target,'div','','grid');for(const [label,value] of [['DOI 總數',r.doi_total],['已探索 DOI',r.discovered],['尚未探索 DOI',r.discovery_unvisited],['有 OA 候選論文',r.with_oa_candidates],['暫未找到 OA',r.no_oa_found_yet],['候選來源 URL',r.source_candidates],['本輪來源已訪／政策阻擋',r.source_attempted_this_cycle],['本輪來源尚未遍歷',r.source_unvisited],['v4 成功解析論文',r.parsed_papers],['等待重試來源',r.retry_waiting]]){const c=add(grid,'article','','card');add(c,'div',String(label),'muted');add(c,'div',String(value??'未知'),'metric')}add(target,'p',r.completion_definition,'muted');add(target,'p','來源探索範圍：'+r.discovery_scope,'muted');add(target,'p','下次接續：每 3 小時 cron（running 才執行）；cycle_complete 後低頻追蹤。','muted');add(target,'h3','各階段與失敗類別');add(target,'pre',JSON.stringify({states:r.source_states,failures:r.failure_classes},null,2));add(target,'p','此進度可先於網站發布保存；上線資料及最後成功發布時間以網站快照為準。','muted')}catch{target.textContent='進度暫時無法讀取，請由 GitHub Actions 查看。'}}
async function loadFields(){const target=document.querySelector('#field-coverage');if(!target)return;try{const [r,ev]=await Promise.all([fetch(base+'data/field_coverage.json').then(r=>r.json()),fetch(base+'data/evaluation.json').then(r=>r.json())]);target.replaceChildren();add(target,'p',`v4 已解析 ${r.parsed_papers} / 索引 ${r.indexed_denominator} 篇；${r.variable_records} 筆變數／衡量。下列分母是已處理範圍，不是全期刊覆蓋率。`,'notice');for(const [label,fields] of [['論文欄位',r.paper_fields],['變數欄位',r.variable_fields]]){const d=add(target,'details','');add(d,'summary',String(label));const table=add(d,'table','');for(const [name,raw] of Object.entries(fields as any)){const f:any=raw;const tr=add(table,'tr','');add(tr,'th',name);add(tr,'td',`${f.known} / ${f.denominator} (${f.coverage===null?'未知':(f.coverage*100).toFixed(1)+'%'})`);add(tr,'td',JSON.stringify(f.missing_reasons))}}const d=add(target,'details','');add(d,'summary','獨立評估：方法、樣本數與精確率／召回率');add(d,'pre',JSON.stringify(ev,null,2));add(target,'p','對齊成功不是語意正確率；未有獨立評估者不報告準確度。','muted')}catch{target.textContent='欄位報告尚未發布或無法載入。'}}
void Promise.all([loadCrawl(),loadFields()]);
