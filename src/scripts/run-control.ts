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
