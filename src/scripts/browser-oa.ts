/** Browser-only OA access: no GitHub workflow, token or additional page. */
const PDFJS='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs';
const PDFWORKER='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs';
const MAX_BYTES=22_000_000, MAX_PAGES=65, MAX_CANDIDATES=8;
type Page={page:number;text:string};
type Evidence={label:string;excerpt:string;page:number;kind:string};
export type OAExtract={
 status:string;source_url:string|null;open_access:boolean;pages:number;
 attempts:Array<{url:string;status:string}>;
 fields:Record<string,{value:string|null;page:number|null;excerpt:string|null;status:string}>;
 hypotheses:Evidence[];findings:Evidence[];robustness:Evidence[];
 report:string;
};
const tidy=(s:string)=>s.replace(/\s+/g,' ').trim();
const doiOk=(s:string)=>/^10\.1002\/smj\.\d+[a-z0-9-]*$/i.test(s);
function safeURL(s:unknown):string|null{
 try{if(typeof s!=='string'||s.length>2000)return null;
   const u=new URL(s);
   if(u.protocol!=='https:'||u.username||u.password||u.port)return null;
   if(/^(localhost|127\.|0\.|10\.|192\.168\.|169\.254\.)/.test(u.hostname))return null;
   return u.toString();
 }catch{return null;}
}
function publisherOA(raw:any){
 if(raw?.open_access?.is_oa&&['gold','hybrid'].includes(raw?.open_access?.oa_status))return true;
 for(const x of [...(raw?.locations||[]),raw?.best_oa_location,raw?.primary_location]){
   if(x?.is_oa&&(x.is_published||x.version==='publishedVersion')&&
     /https:\/\/(?:sms\.)?onlinelibrary\.wiley\.com\//i.test(x.landing_page_url||x.pdf_url||''))return true;
 }
 return false;
}
async function openAlexMetadata(doi:string,id:unknown){
 const target=typeof id==='string'&&/^https:\/\/openalex\.org\/W\d+$/.test(id)?
    id.split('/').pop():'https://doi.org/'+doi;
 try{
   const r=await fetch('https://api.openalex.org/works/'+encodeURI(target!)+
     '?select=id,doi,open_access,locations,best_oa_location,primary_location',
     {signal:AbortSignal.timeout(9000),headers:{Accept:'application/json'}});
   if(!r.ok)return null;
   const raw=await r.json();
   return String(raw.doi||'').toLowerCase()==='https://doi.org/'+doi.toLowerCase()?raw:null;
 }catch{return null;}
}
function candidatesFor(paper:any,raw:any){
 const locations=[...(paper.enrichment?.oa_locations||[])];
 for(const l of [...(raw?.locations||[]),raw?.best_oa_location,raw?.primary_location]){
   if(l?.is_oa&&(l.is_published||l.is_accepted||['acceptedVersion','publishedVersion'].includes(l.version)))locations.push(l);
 }
 if(publisherOA(raw)&&doiOk(paper.doi))
   locations.push({is_oa:true,is_published:true,
     pdf_url:'https://sms.onlinelibrary.wiley.com/doi/pdfdirect/'+paper.doi});
 const urls=new Map<string,{url:string;kind:'pdf'|'html';restricted:boolean}>();
 for(const l of locations){
   if(!l?.is_oa||!(l.is_published||l.is_accepted||
     ['acceptedVersion','publishedVersion'].includes(l.version)))continue;
   for(const [field,kind] of [['pdf_url','pdf'],['landing_page_url','html']] as const){
     const url=safeURL(l[field]);if(!url)continue;
     const host=new URL(url).hostname;
     urls.set(url,{url,kind,restricted:/(wiley\.com|jstor\.org|ssrn\.com)$/.test(host)});
   }
 }
 return [...urls.values()].sort((a,b)=>Number(a.restricted)-Number(b.restricted)||
   Number(a.kind!=='pdf')-Number(b.kind!=='pdf')).slice(0,MAX_CANDIDATES);
}
async function pdfPages(bytes:ArrayBuffer):Promise<Page[]>{
 // Pin the PDF.js API and worker to the exact same Apache-2.0 release.
 const pdfjs:any=await import(/* @vite-ignore */ PDFJS);
 pdfjs.GlobalWorkerOptions.workerSrc=PDFWORKER;
 const loading=pdfjs.getDocument({data:new Uint8Array(bytes),useSystemFonts:true});
 const pdf=await loading.promise,pages:Page[]=[];
 try{
   for(let i=1;i<=Math.min(pdf.numPages,MAX_PAGES);i++){
     const page=await pdf.getPage(i),content=await page.getTextContent();
     let text='';
     for(const x of content.items)if('str' in x)
       text+=String(x.str||'')+(x.hasEOL?'\n':' ');
     pages.push({page:i,text});page.cleanup();
   }
 }finally{await pdf.destroy();}
 return pages;
}
function htmlPages(html:string):Page[]{
 const doc=new DOMParser().parseFromString(html,'text/html');
 doc.querySelectorAll('script,style,nav,footer,header,aside,form').forEach(x=>x.remove());
 const article=doc.querySelector('article')||doc.querySelector('main')||doc.body;
 if(!article)throw Error('not_article_html');
 const arr:Array<Page>=[];
 for(const x of article.querySelectorAll('h1,h2,h3,h4,p,li,tr')){
   const text=tidy(x.textContent||'');
   if(text.length>30&&text.length<3500)arr.push({page:arr.length+1,text});
 }
 return arr;
}
function validate(paper:any,pages:Page[]){
 const first=tidy(pages.slice(0,10).map(p=>p.text).join(' ')).toLowerCase();
 const terms=[...new Set((paper.title||'').toLowerCase().match(/[a-z]{4,}/g)||[])];
 const fraction=terms.filter(x=>first.includes(x)).length/Math.max(1,terms.length);
 const doi=first.includes(paper.doi.toLowerCase());
 const author=(paper.authors||[]).some((a:string)=>first.includes(a.trim().split(' ').at(-1)?.toLowerCase()||'__none__'));
 if(!((doi&&fraction>=.4)||(fraction>=.7&&author)))throw Error('article_identity_mismatch');
 if(pages.reduce((sum,p)=>sum+p.text.length,0)<2200)throw Error('not_full_article');
}
function extract(paper:any,pages:Page[],source_url:string):OAExtract{
 const sentences:Array<{page:number;text:string;section:string}>=[];
 let section='unknown';
 for(const page of pages){
   const lines=page.text.split(/\n+/).map(tidy);
   for(const line of lines){
     if(/^(?:\d+(?:\.\d+)?[ .-]*)?(introduction|literature review|hypotheses?|theoretical (?:background|development|framework)|methods?|data(?: and methods)?|measurement|results?|discussion|robustness|sensitivity|conclusion|references)\b/i.test(line)&&line.length<95)
       section=line.toLowerCase();
     if(/^(references|bibliography|appendix)/i.test(section))continue;
     for(const part of line.split(/(?<=[.!?])\s+(?=[A-Z])/))
       if(part.length>30)sentences.push({page:page.page,text:part,section});
   }
 }
 const quote=(s:string)=>tidy(s).slice(0,230);
 const field=(sample:typeof sentences[number]|undefined,value:string|null)=>{
   return {value,status:sample?'fulltext_lexical_evidence':'unknown',
     page:sample?.page||null,excerpt:sample?quote(sample.text):null};
 };
 const period=sentences.find(p=>/\b(?:19|20)\d{2}\s*(?:-|–|to|through|and)\s*(?:19|20)\d{2}\b/i.test(p.text)&&
   /\b(?:sample|period|data|panel|study|years|firms)\b/i.test(p.text+' '+p.section));
 const years=period?.text.match(/\b((?:19|20)\d{2})\s*(?:-|–|to|through|and)\s*((?:19|20)\d{2})\b/i);
 const periodValid=years&&Number(years[2])>=Number(years[1])&&Number(years[2])-Number(years[1])<=60;
 const dbs=['Compustat','ExecuComp','BoardEx','CRSP','Orbis','FactSet','Thomson Reuters',
   'Institutional Shareholder Services','ISS','NBER','USPTO','Patent Data Project','PATSTAT'];
 const data=sentences.find(p=>dbs.some(d=>p.text.toLowerCase().includes(d.toLowerCase()))&&
   /\b(data|sample|measure|variable|availability|research design|method)\b/i.test(p.text+' '+p.section));
 const dbNames=data?dbs.filter(d=>data.text.toLowerCase().includes(d.toLowerCase())):[];
 const methods=['negative binomial','poisson','fixed effects','ordinary least squares','OLS regression',
   'logistic regression','panel regression','generalized estimating equations','instrumental variables',
   'difference-in-differences','event study','random effects','tobit regression','probit regression'];
 const method=sentences.find(p=>methods.some(x=>p.text.toLowerCase().includes(x))&&
   /\b(we|our|estimate|regression|method|model|analysis|used|data)\b/i.test(p.text));
 const matchedMethod=methods.find(x=>method?.text.toLowerCase().includes(x))||null;
 const hypotheses:Evidence[]=[],findings:Evidence[]=[],robustness:Evidence[]=[];
 const unique=new Set<string>();
 function add(arr:Evidence[],p:typeof sentences[number],kind:string,label:string,max:number){
   const key=kind+'|'+p.page+'|'+p.text.slice(0,80);
   if(unique.has(key)||arr.length>=max)return;
   unique.add(key);arr.push({label,kind,page:p.page,excerpt:quote(p.text)});
 }
 for(const p of sentences){
   const h=p.text.match(/\b(?:Hypothesis|H)\s*(\d+[a-z]?)\s*[:.]\s*\S/i);
   const prop=p.text.match(/\b(?:Proposition|P)\s*(\d+[a-z]?)\s*[:.]\s*\S/i);
   if(h)add(hypotheses,p,'hypothesis','H'+h[1],10);
   else if(prop)add(hypotheses,p,'proposition','P'+prop[1],10);
   if(/\b(?:we (?:further |also )?(?:find|found|demonstrate|show|report)|our (?:findings|results) (?:show|suggest|indicate)|results (?:show|suggest|indicate)|we find support)\b/i.test(p.text))
     add(findings,p,'finding','作者發現句',7);
   if(/\b(?:robust(?:ness)? (?:checks?|tests?|results?)|sensitivity (?:analysis|analyses|test)|results? remain(?:ed)? robust|alternative specifications)\b/i.test(p.text))
     add(robustness,p,'robustness','穩健性文字',8);
 }
 return {status:'parsed',source_url,open_access:true,pages:pages.length,attempts:[],
   fields:{
     sample_period:field(periodValid?period:undefined,periodValid?years![1]+'–'+years![2]:null),
     data_source:field(data,dbNames.length?dbNames.join(', '):null),
     empirical_method:field(method,matchedMethod)
   },hypotheses,findings,robustness,
   report:'瀏覽器已即時下載並解析合法 OA 文字；欄位為原文詞組辨識，不等於學者人工驗證或完整統計重現。'};
}
async function fetchSource(paper:any,candidate:{url:string;kind:'pdf'|'html'}):Promise<OAExtract>{
 const r=await fetch(candidate.url,{mode:'cors',signal:AbortSignal.timeout(20000)});
 if(!r.ok)throw Error('http_'+r.status);
 if(Number(r.headers.get('content-length')||0)>MAX_BYTES)throw Error('document_too_large');
 const bytes=await r.arrayBuffer();
 if(bytes.byteLength>MAX_BYTES)throw Error('document_too_large');
 const pdf=bytes.byteLength>=4&&new TextDecoder('ascii').decode(bytes.slice(0,4))==='%PDF';
 const pages=pdf?await pdfPages(bytes):
  (r.headers.get('content-type')||'').includes('html')||candidate.kind==='html'?
    htmlPages(new TextDecoder().decode(bytes)):[];
 if(!pages.length)throw Error('not_pdf_or_article_html');
 validate(paper,pages);
 return extract(paper,pages,r.url);
}
export async function analyzeBrowserOA(paper:any,onStatus:(s:string)=>void):Promise<OAExtract>{
 const fail=(status:string,attempts:OAExtract['attempts'],oa:boolean,report:string):OAExtract=>({
   status,source_url:null,open_access:oa,pages:0,attempts,report,
   fields:Object.fromEntries(['sample_period','data_source','empirical_method'].map(k=>
     [k,{value:null,excerpt:null,page:null,status:'unknown'}])),
   hypotheses:[],findings:[],robustness:[]});
 if(!doiOk(paper.doi))return fail('invalid_doi',[],false,'無法確認為 SMJ DOI。');
 onStatus('正在向 OpenAlex 取得最新的 Open Access 全文來源…');
 const raw=await openAlexMetadata(paper.doi,paper.enrichment?.openalex_id);
 const sources=candidatesFor(paper,raw);
 const oa=sources.length>0||!!raw?.open_access?.is_oa;
 if(!sources.length)return fail('no_oa_download_url',[],oa,'目前沒有可直接下載的 OA PDF／HTML 網址；OA 標記不等於可用全文網址。');
 const attempts:OAExtract['attempts']=[],started=Date.now();
 for(const item of sources){
   if(Date.now()-started>80000)break;
   onStatus('正在下載並檢查 OA 全文（'+(attempts.length+1)+'／'+sources.length+'）：'+new URL(item.url).hostname);
   try{
     const result=await fetchSource(paper,item);
     return {...result,attempts:[...attempts,{url:item.url,status:'parsed'}]};
   }catch(e){
     const text=e instanceof Error?e.message:'browser_fetch_failed';
     attempts.push({url:item.url,status:/Failed to fetch|NetworkError|Load failed/i.test(text)?
       'browser_cors_or_network_blocked':text.slice(0,100)});
   }
 }
 return fail('oa_fetch_blocked',attempts,oa,
   '雖找到 OA 來源，但來源未允許此網站的瀏覽器跨網域讀取，或全文身份／格式驗證失敗。這不表示文章不是 OA。');
}
