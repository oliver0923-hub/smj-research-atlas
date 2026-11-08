/**
 * Single-click, source-constrained analysis on the public static paper page.
 *
 * No GitHub token, no write API, no fake server-side PDF parsing. The button
 * immediately analyses existing source-aligned Atlas data and the OpenAlex
 * abstract already retrieved in the browser. Existing GitHub issue results
 * are read-only and optional. New deep crawling still needs authenticated
 * GitHub issue submission because GitHub Pages has no trusted backend.
 */
const REPO='oliver0923-hub/smj-research-atlas';
const FIELDS=['sample_period','data_source','empirical_method'] as const;
const FIELD_LABELS:Record<string,string>={
  sample_period:'研究樣本期間',
  data_source:'資料來源',
  empirical_method:'實證研究方法',
};
const RESEARCH_LABELS:Record<string,string>={
  hypotheses:'假設／理論命題',
  findings:'作者報告的實證結果',
  checks:'穩健性／敏感性檢驗',
};

function node(parent:Element,tag:string,text?:string,cls?:string):HTMLElement{
  const result=document.createElement(tag);
  if(text!==undefined)result.textContent=text;
  if(cls)result.className=cls;
  parent.append(result);
  return result;
}

function safeDoi(raw:any){
  const s=String(raw||'').toLowerCase().trim();
  return /^10\.\d{4,9}\/[a-z0-9._;()/:+-]+$/.test(s)?s:null;
}

function abstractSentences(text:string):string[]{
  // A lexical evidence slice, NOT semantic inference. De-duplicate repeated
  // Research Summary / Managerial Summary statements.
  const rows=text.replace(/\s+/g,' ').split(/(?<=[.!?])\s+(?=[A-Z])/);
  return [...new Set(rows.map(x=>x.trim()).filter(x=>x.length>25&&x.length<650))];
}

function evidenceLink(parent:Element,source:string,page?:number|null){
  if(!/^https:\/\//.test(source))return;
  const a=node(parent,'a','查看來源文字','tiny') as HTMLAnchorElement;
  a.href=source+(page?'#page='+page:'');
  a.target='_blank';a.rel='noopener noreferrer';
}

function fieldDetails(parent:Element,k:string,raw:any,review:boolean,abstract:string|null,sourceUrl:string){
  const value=raw?.value;
  if(value!==undefined&&value!==null){
    node(parent,'strong',Array.isArray(value)?value.join('–'):typeof value==='object'?JSON.stringify(value):String(value));
    node(parent,'p','E2 · 已有可對齊的原文擷取欄位（非專家人工複核）','tiny');
    return;
  }
  if(k==='data_source' && abstract){
    const cue=abstractSentences(abstract).find(s=>
       /\b(?:using|based on|drawn from|obtained from|collected from|data from|using the)\b.{0,95}\b(?:data|dataset|transactions|records|sample)\b/i.test(s)
       || /\b(?:NBA|National Basketball Association|Compustat|CRSP|Orbis|FactSet|survey data)\b/i.test(s));
    if(cue){
      node(parent,'strong','摘要提供資料線索（E1）');
      node(parent,'p',cue.length>250?cue.slice(0,250)+'…':cue,'evidence');
      node(parent,'p','只能確認摘要提及的資料，不代表已查證實際資料庫、樣本期間或變數來源。','tiny');
      evidenceLink(parent,sourceUrl);
      return;
    }
  }
  if(review){
    node(parent,'strong','暫定不適用於原創實證估計');
    node(parent,'p','依標題判定為 Review／Synthesis；仍須全文核查文獻檢索範圍與回顧方法。','tiny');
  }else{
    node(parent,'strong','未知／尚無來源證據');
    node(parent,'p','沒有足夠原文可確認；不是零值，也不表示研究沒有使用。','tiny');
  }
}

function localResearchRows(parent:Element,records:any[],evidenceById:Map<string,any>,name:string){
  node(parent,'h4',RESEARCH_LABELS[name]||name);
  if(!records.length){
    node(parent,'p','目前沒有可對齊的正文紀錄；不代表原文不存在。','muted');
    return;
  }
  for(const r of records.slice(0,10)){
    const el=node(parent,'article',undefined,'record');
    const label=r.label||r.hypothesis_label||r.kind||r.hypothesis_id||name;
    node(el,'strong',String(label));
    if(r.summary||r.test_summary)node(el,'p',String(r.summary||r.test_summary));
    if(r.reported_support)node(el,'p','作者報告的支持判定：'+r.reported_support,'tiny');
    if(r.result)node(el,'p','穩健性結果：'+r.result,'tiny');
    const ev=(r.evidence_ids||[]).map((id:string)=>evidenceById.get(id)).find(Boolean);
    if(ev){
      node(el,'p',String(ev.quoted_excerpt||'保留來源位置；無可顯示的短摘錄').slice(0,250),'evidence');
      node(el,'p','E2 · '+String(ev.section||'來源段落')+' · page '+(ev.page??'HTML'),'tiny');
      evidenceLink(el,ev.source_url,ev.page);
    }
  }
}

function existingLegacyClaims(parent:Element,claims:any[],sourceUrl:string){
  for(const [kind,label] of [['hypothesis','假設'],['proposition','命題'],['finding','結果'],['robustness','穩健性'],['sensitivity','敏感性']]){
    const rows=claims.filter(x=>x.claim_type===kind);
    if(!rows.length)continue;
    node(parent,'h4',label+' · '+rows.length+' 筆');
    for(const x of rows.slice(0,8)){
      const c=node(parent,'article',undefined,'record');
      node(c,'strong',String(x.label||x.hypothesis_label||label));
      node(c,'p',String(x.statement_excerpt||'來源描述未提供').slice(0,250),'evidence');
      node(c,'p','來源文字線索，並非人工審閱','tiny');
      evidenceLink(c,x.source_url||sourceUrl,x.source_page);
    }
  }
}

function abstractFindings(parent:Element,abstract:string|null,sourceUrl:string){
  node(parent,'h4','摘要中作者明示的發現（E1，非全文結果表）');
  if(!abstract){
    node(parent,'p','OpenAlex 摘要目前不可取得；不據此推論假設或結果。','muted');
    return;
  }
  const sentences=abstractSentences(abstract).filter(s=>
    /\b(?:we (?:also )?(?:find|found|show|demonstrate|reveal)|our (?:results|findings) (?:show|suggest|indicate|reveal)|results (?:show|suggest|indicate|reveal)|we (?:further )?show)\b/i.test(s));
  if(!sentences.length){
    node(parent,'p','摘要未出現可明確對齊的作者發現句；實證結果仍待查證。','muted');
    return;
  }
  for(const sentence of sentences.slice(0,8)){
    const c=node(parent,'article',undefined,'record');
    node(c,'p',sentence.slice(0,400),'evidence');
    node(c,'p','E1 · 作者摘要陳述；非係數、顯著性或穩健性證據','tiny');
    evidenceLink(c,sourceUrl);
  }
}

async function loadGitHubAnalysis(doi:string){
  const q='repo:'+REPO+' is:issue in:title "Atlas analyze: '+doi+'"';
  const api='https://api.github.com';
  const headers={Accept:'application/vnd.github+json'};
  const r=await fetch(api+'/search/issues?q='+encodeURIComponent(q)+'&per_page=20',{headers});
  if(!r.ok)throw new Error('GitHub public API HTTP '+r.status);
  const data=await r.json();
  const issue=(data.items||[]).find((x:any)=>
    x.title==='Atlas analyze: '+doi
    && x.user?.login==='oliver0923-hub'
    && !x.pull_request);
  if(!issue)return null;
  const c=await fetch(api+'/repos/'+REPO+'/issues/'+issue.number+'/comments?per_page=100',{headers});
  if(!c.ok)throw new Error('GitHub issue comments HTTP '+c.status);
  const comments=await c.json();
  const comment=[...comments].reverse().find((x:any)=>
    x.user?.login==='github-actions[bot]' &&
    typeof x.body==='string'&&x.body.includes('## 單篇 SMJ 研究資料擷取結果'));
  const status=comment?.body?.match(/\*\*執行狀態：\*\*\s*\\?\x60([^\\\x60]+)\\?\x60/)?.[1]||'等待 GitHub 工作結果';
  return {html_url:issue.html_url,number:issue.number,status,comment_url:comment?.html_url||issue.html_url};
}

function reportGitHubStatus(parent:Element,doi:string,issueURL:string){
  const region=node(parent,'div',undefined,'record');
  node(region,'h4','GitHub 全文擷取任務');
  const status=node(region,'p','查詢這篇 DOI 是否已有全文分析紀錄…','muted');
  void (async()=>{
    try{
      const record=await loadGitHubAnalysis(doi);
      if(record){
        status.textContent='已找到 Issue #'+record.number+' · 最近的全文擷取狀態：'+record.status;
        const a=node(region,'a','查看完整 GitHub 分析報告與來源紀錄') as HTMLAnchorElement;
        a.href=record.comment_url;a.target='_blank';a.rel='noopener noreferrer';
      }else{
        status.textContent='尚未找到此 DOI 的 GitHub 全文擷取 Issue。';
      }
    }catch{
      status.textContent='GitHub 公開結果暫時無法讀取；不影響上方的頁內分析。';
    }
    const a=node(region,'a','需要重新抓取／解析全文？前往 GitHub 確認提交任務') as HTMLAnchorElement;
    a.href=issueURL;a.target='_blank';a.rel='noopener noreferrer';
    node(region,'p','GitHub Pages 是靜態網站：不能在未經授權的情況下直接建立 Issue 或執行 GitHub Actions。此連結會開啟預填表單，須由專案擁有者提交。','tiny');
  })();
}

/** User click -> immediate inline evidence display. No credential or paid API. */
export async function renderInPageAnalysis(
  parent:HTMLElement,paper:any,abstractPromise:Promise<string|null>|undefined,issueURL:string
){
  parent.replaceChildren();
  parent.setAttribute('aria-live','polite');
  const progress=node(parent,'p','整理 Atlas 的逐篇來源與 OpenAlex 摘要…','status-line');
  let abstract:string|null=null;
  try{abstract=await abstractPromise||null;}catch{abstract=null;}
  parent.replaceChildren();
  const record=paper.research_v4;
  const typeIsReview=/\b(?:strategic management review|literature review|systematic review|meta.analysis|bibliometric review)\b/i.test(paper.title);
  const original='https://doi.org/'+encodeURIComponent(paper.doi);
  node(parent,'h3','這篇論文的即時證據分析');
  node(parent,'p',
    record?'已有可對齊的合法正文紀錄；同時參照摘要。':'目前只使用已索引書目及可取得的 OpenAlex 摘要，沒有假裝解析出版社完整 PDF。',
    'notice');
  node(parent,'p','論文類型：'+(typeIsReview?'Review／Synthesis（標題推定，非全文查核）':
      '研究論文／概念論文類型尚待核查'),'status-line');
  node(parent,'h4','研究設計欄位');
  const grid=node(parent,'div',undefined,'data-table');
  const t=node(grid,'table');const h=node(t,'thead');const tr=node(h,'tr');
  for(const label of ['欄位','值與證據'])node(tr,'th',label);
  const body=node(t,'tbody');
  for(const k of FIELDS){
    const row=node(body,'tr');node(row,'td',FIELD_LABELS[k]+' ('+k+')');
    const cell=node(row,'td');
    fieldDetails(cell,k,record?.fields?.[k],typeIsReview,abstract,original);
  }
  node(parent,'h4','假設與理論命題');
  if(record){
    const evidence=new Map<string,any>((record.evidence||[]).map((x:any)=>[x.evidence_id,x]));
    localResearchRows(parent,record.hypotheses||[],evidence,'hypotheses');
    localResearchRows(parent,record.findings||[],evidence,'findings');
    localResearchRows(parent,record.checks||[],evidence,'checks');
  }else{
    const claims=paper.study_claims||[];
    if(claims.length)existingLegacyClaims(parent,claims,original);
    else node(parent,'p','H1／H2、命題與其檢驗狀態目前未知：摘要的發現句不能當成原文正式假設。','muted');
    abstractFindings(parent,abstract,original);
    node(parent,'h4','穩健性／敏感性檢驗');
    if(!claims.some((x:any)=>x.claim_type==='robustness'||x.claim_type==='sensitivity')){
      node(parent,'p','目前沒有可靠的正文穩健性證據，不能判定研究是否執行或結果是否成立。','muted');
    }
  }
  const doi=safeDoi(paper.doi);
  if(doi)reportGitHubStatus(parent,doi,issueURL);
  progress.remove();
}
