import {analyzeBrowserOA,type OAExtract} from './browser-oa';
/**
 * Single-click, source-constrained analysis on the public static paper page.
 *
 * Original PDF/HTML bytes are fetched through the bounded DOI-only gateway
 * or a CORS-enabled OA source. Parsing and evidence display stay in this page.
 * The gateway has no GitHub token; existing E2 or E1 data are fallback only.
 */
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
  if(review){
    node(parent,'strong','暫定不適用於原創實證估計');
    node(parent,'p','依標題判定為 Review／Synthesis；仍須全文核查文獻檢索範圍與回顧方法。','tiny');
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
  node(parent,'strong','未知／尚無來源證據');
  node(parent,'p','沒有足夠原文可確認；不是零值，也不表示研究沒有使用。','tiny');
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

function renderParsedOA(parent:Element,oa:OAExtract,review:boolean){
  const summary=node(parent,'p',oa.report,'notice');
  node(parent,'p','OA 來源：已找到 · 全文下載：'+(oa.downloaded?'成功（'+oa.parsed_bytes?.toLocaleString()+' bytes）':'未知')+' · 論文身分：'+(oa.identity_verified?'已驗證':'未驗證')+' · 原文解析：成功','status-line');
  node(parent,'p',oa.format==='pdf'?'已在本頁直接解析 '+oa.pages+' 頁 PDF':'已在本頁直接解析 '+oa.pages+' 個 HTML 文字段落；不儲存或重新發布全文','status-line');
  if(oa.partial)node(parent,'p','本次僅掃描前 '+oa.pages+'／'+oa.total_pages+' 頁；後續頁面尚未解析，不是全文完整覆蓋。','notice');
  node(parent,'p','Provider 授權標記：'+(oa.license||'未知')+' · Provider 版本：'+(oa.source_version||'未知')+' · SHA256：'+(oa.source_hash||'未知'),'tiny');
  if(oa.source_url)evidenceLink(parent,oa.source_url);
  function proof(target:Element,x:any){
    const d=node(target,'details');node(d,'summary',x.label+' · '+(oa.format==='pdf'?'PDF 第 '+x.page+' 頁':'HTML 第 '+x.page+' 段')+' · '+(x.section||'章節未辨識'));
    node(d,'p',x.excerpt||'本篇短引文額度已用盡，仍保留原文位置與來源 hash。','evidence');
    node(d,'p','E2 · 詞組／位置核對，可信程度尚未校準；非人工複核。','tiny');
    if(x.span_hash)node(d,'p','原文片段 SHA256：'+x.span_hash+' · offset '+x.offset_start+'–'+x.offset_end,'tiny');
    if(oa.source_url)evidenceLink(d,oa.source_url,oa.format==='pdf'?x.page:null);
  }
  node(parent,'h4','研究設計與方法（全文詞組對齊）');
  const table=node(parent,'table'),header=node(table,'thead'),tr=node(header,'tr');
  node(tr,'th','欄位');node(tr,'th','擷取結果／原文來源');
  const body=node(table,'tbody');
  for(const k of FIELDS){
    const cellRow=node(body,'tr');node(cellRow,'td',FIELD_LABELS[k]+' ('+k+')');
    const cell=node(cellRow,'td');const f=oa.fields[k];
    if(f?.value){
      node(cell,'strong',f.value);
      if(!f.evidence?.length&&f.excerpt)node(cell,'p',f.excerpt,'evidence');
      node(cell,'p','E2 · 合法全文自動詞組比對 · '+(oa.format==='pdf'?'PDF 第 '+f.page+' 頁':'HTML 第 '+f.page+' 段')+' · 非人工驗證','tiny');
      if(f.evidence?.length)f.evidence.forEach(x=>proof(cell,x));
      else if(oa.source_url)evidenceLink(cell,oa.source_url,oa.format==='pdf'?f.page:null);
    }else if(review){
      node(cell,'strong','暫定不適用於原創實證估計');
      node(cell,'p','此篇依標題判斷為回顧文章；文獻檢索方法仍需另行辨識。','tiny');
    }else{
      node(cell,'strong','未從本次可解析文字確認');
      node(cell,'p',f?.reason||'沒有可靠文字命中，不代表作者沒有報告此資訊。','tiny');
      f?.evidence?.forEach(x=>proof(cell,x));
    }
  }
  for(const [key,label] of [['hypotheses','假設／命題'],['findings','實證發現'],['robustness','穩健性／敏感性檢驗'],['theories','Theory：作者自述使用／僅提及'],['constructs','Construct：原文明示的操作化構念']] as const){
    const entries=oa[key]||[];
    node(parent,'h4',label+' · '+entries.length+' 筆原文線索');
    if(!entries.length){
      node(parent,'p','本次文字擷取未能可靠定位；不代表原文沒有。','muted');
      continue;
    }
    for(const x of entries){
      const row=node(parent,'article',undefined,'record');
      node(row,'strong',x.label);
      node(row,'p','類型：'+x.kind,'tiny');
      if(x.support_status)node(row,'p','假設支持：'+x.support_status+' · 統計顯著：'+(x.significance||'unknown')+'（兩者獨立，不推定模型對應）','tiny');
      proof(row,x);
      node(row,'p','E2 · '+(oa.format==='pdf'?'PDF 第 '+x.page+' 頁':'HTML 第 '+x.page+' 段')+' · 機器搜尋所得，不保證與統計模型對應','tiny');
      if(oa.source_url)evidenceLink(row,oa.source_url,oa.format==='pdf'?x.page:null);
    }
  }
}

/** Clicking immediately fetches legal OA sources and analyses PDF/HTML in-browser. */
export async function renderInPageAnalysis(
 parent:HTMLElement,paper:any,abstractPromise:Promise<string|null>|undefined
){
  parent.replaceChildren();
  parent.setAttribute('aria-live','polite');
  const progress=node(parent,'p','開始查詢 Open Access 全文來源…','status-line');
  const oaPromise=analyzeBrowserOA(paper,(status)=>{progress.textContent=status;});
  let abstract:string|null=null;
  let oa:OAExtract;
  try{oa=await oaPromise;}catch(e){
    oa={status:'browser_error',source_url:null,open_access:false,pages:0,format:null,
       attempts:[],fields:{},hypotheses:[],findings:[],robustness:[],
       report:e instanceof Error?e.message:'瀏覽器全文讀取失敗'};
  }
  parent.replaceChildren();
  const record=paper.research_v4;
  const review=/\b(?:strategic management review|literature review|systematic review|meta.analysis|bibliometric review)\b/i.test(paper.title);
  const original='https://doi.org/'+encodeURIComponent(paper.doi);
  node(parent,'h3','這篇論文的全文與來源分析');
  if(oa.status==='parsed'){
    renderParsedOA(parent,oa,review);
    return;
  }
  try{abstract=await abstractPromise||null;}catch{abstract=null;}
  node(parent,'p','OA 全文直接讀取狀態：'+oa.status,'status-line');
  node(parent,'p','OA 來源：'+(oa.open_access?'已找到來源／OA 標記':'尚未確認')+' · 全文下載：'+(oa.downloaded?'收到位元組，但未通過解析驗證':'尚未成功')+' · 全文解析：尚未成功','status-line');
  node(parent,'p',oa.report,'notice');
  if(oa.attempts.length){
    const details=node(parent,'details');
    node(details,'summary','查看這次 OA 全文存取結果（'+oa.attempts.length+' 個來源）');
    for(const a of oa.attempts.slice(0,8)){
      const entry=node(details,'p',a.status+' · ','tiny');
      evidenceLink(entry,a.url);
    }
  }
  node(parent,'p','以下提供既有 Atlas 資料／OpenAlex 摘要支持的較低證據層級分析；這不是已成功讀取完整 PDF。','muted');
  node(parent,'h4','研究設計欄位');
  const table=node(parent,'table'),header=node(table,'thead'),head=node(header,'tr');
  node(head,'th','欄位');node(head,'th','值與證據');
  const body=node(table,'tbody');
  for(const k of FIELDS){
    const row=node(body,'tr');
    node(row,'td',FIELD_LABELS[k]+' ('+k+')');
    const cell=node(row,'td');
    fieldDetails(cell,k,record?.fields?.[k],review,abstract,original);
  }
  if(record){
    const evidence=new Map<string,any>((record.evidence||[]).map((x:any)=>[x.evidence_id,x]));
    for(const key of ['hypotheses','findings','checks'])
      localResearchRows(parent,record[key]||[],evidence,key);
  }else{
    const claims=paper.study_claims||[];
    if(claims.length)existingLegacyClaims(parent,claims,original);
    else node(parent,'p','目前無正文證據可確認 H1、H2 或正式命題。','muted');
    abstractFindings(parent,abstract,original);
    node(parent,'h4','穩健性／敏感性檢驗');
    if(!claims.some((x:any)=>['robustness','sensitivity'].includes(x.claim_type)))
      node(parent,'p','目前無正文穩健性證據；不能判定是否執行。','muted');
  }
}
