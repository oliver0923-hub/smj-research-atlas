/** Original-byte OA analysis in this page; optional DOI-only managed retrieval. */
const GATEWAY='https://smj-oa-gateway-oliver.oliver0923.chatgpt.site/api/document';
const PDFJS='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs';
const PDFWORKER='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs';
const MAX_BYTES=22_000_000, MAX_PAGES=65, MAX_CANDIDATES=8;
export type Page={page:number;text:string};
export type Evidence={label:string;excerpt:string;page:number;kind:string;section?:string;support_status?:string;significance?:string;confidence?:string;span_hash?:string;offset_start?:number;offset_end?:number};
export type OAExtract={
 status:string;source_url:string|null;open_access:boolean;pages:number;format:'pdf'|'html'|null;
 attempts:Array<{url:string;status:string}>;
 fields:Record<string,{value:string|null;page:number|null;excerpt:string|null;status:string;evidence?:Evidence[];reason?:string}>;
 hypotheses:Evidence[];findings:Evidence[];robustness:Evidence[];
 report:string;downloaded?:boolean;identity_verified?:boolean;parsed_bytes?:number;source_hash?:string;
 license?:string;source_version?:string;total_pages?:number;partial?:boolean;
 theories?:Evidence[];constructs?:Evidence[];
};
const tidy=(s:string)=>s.replace(/\s+/g,' ').trim();
const doiOk=(s:string)=>/^10\.1002\/smj\.\d+[a-z0-9-]*$/i.test(s);
const TRUSTED_HOSTS=new Set(['www.econstor.eu','econstor.eu','repositorio.ie.edu','lbsresearch.london.edu','openaccess.city.ac.uk','ora.ox.ac.uk','research-repository.st-andrews.ac.uk','onlinelibrary.wiley.com','sms.onlinelibrary.wiley.com']);
export function safeURL(s:unknown):string|null{
 try{if(typeof s!=='string'||s.length>2000)return null;
   const u=new URL(s);
   if(u.protocol!=='https:'||u.username||u.password||u.port)return null;
   if(!TRUSTED_HOSTS.has(u.hostname))return null;
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
export function candidatesFor(paper:any,raw:any){
 const locations=[...(paper.enrichment?.oa_locations||[])];
 for(const l of [...(raw?.locations||[]),raw?.best_oa_location,raw?.primary_location]){
   if(l?.is_oa)locations.push(l);
 }
 if(publisherOA(raw)&&doiOk(paper.doi))
   locations.push({is_oa:true,is_published:true,
     pdf_url:'https://sms.onlinelibrary.wiley.com/doi/pdfdirect/'+paper.doi});
 const urls=new Map<string,{url:string;kind:'pdf'|'html';restricted:boolean}>();
 for(const l of locations){
   const licensedRepository=/^cc-by(?:-nc|-nd|-sa|-nc-nd|-nc-sa)?$|^cc0$|^public-domain$/i.test(l?.license||'')&&
     [l?.pdf_url,l?.landing_page_url].some(u=>{const s=safeURL(u);return s&&!new URL(s).hostname.endsWith('wiley.com');});
   if(!l?.is_oa||!(l.is_published||l.is_accepted||
     ['acceptedVersion','publishedVersion'].includes(l.version)||licensedRepository))continue;
   for(const [field,kind] of [['pdf_url','pdf'],['landing_page_url','html']] as const){
     const url=safeURL(l[field]);if(!url)continue;
     const host=new URL(url).hostname;
     urls.set(url,{url,kind,restricted:/(wiley\.com|jstor\.org|ssrn\.com)$/.test(host)});
   }
 }
 return [...urls.values()].sort((a,b)=>Number(a.restricted)-Number(b.restricted)||
   Number(a.kind!=='pdf')-Number(b.kind!=='pdf')).slice(0,MAX_CANDIDATES);
}
async function pdfPages(bytes:ArrayBuffer):Promise<{pages:Page[];total:number}>{
 // Pin the PDF.js API and worker to the exact same Apache-2.0 release.
 const pdfjs:any=await import(/* @vite-ignore */ PDFJS);
 pdfjs.GlobalWorkerOptions.workerSrc=PDFWORKER;
 const loading=pdfjs.getDocument({data:new Uint8Array(bytes),useSystemFonts:true,isEvalSupported:false,enableXfa:false});
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
 return {pages,total:pdf.numPages};
}
export function htmlPages(html:string):Page[]{
 const doc=new DOMParser().parseFromString(html,'text/html');
 doc.querySelectorAll('script,style,nav,footer,header,aside,form').forEach(x=>x.remove());
 const article=doc.querySelector('article')||doc.querySelector('main');
 if(!article)throw Error('not_article_html');
 const headings=[...article.querySelectorAll('h2,h3,h4')].map(h=>h.textContent||'').join(' ');
 if(!/methods?|measures?|theor\w*|hypothes\w*|sample|data/i.test(headings)||!/results?|discussion|conclusion|appendi/i.test(headings))throw Error('metadata_landing_not_fulltext');
 const arr:Array<Page>=[];
 for(const x of article.querySelectorAll('h1,h2,h3,h4,p,li,tr')){
   const text=tidy(x.textContent||'');
   if(text.length>(/^H[1-4]$/i.test(x.tagName)?0:30)&&text.length<3500)arr.push({page:arr.length+1,text});
 }
 return arr;
}
export function validate(paper:any,pages:Page[]){
 const first=tidy(pages.slice(0,10).map(p=>p.text).join(' ')).toLowerCase();
 const terms:string[]=[...new Set<string>(String(paper.title||'').toLowerCase().match(/[a-z]{4,}/g)||[])];
 const fraction=terms.filter(x=>first.includes(x)).length/Math.max(1,terms.length);
 const doi=first.includes(paper.doi.toLowerCase());
 const author=(paper.authors||[]).some((a:string)=>first.includes(a.trim().split(' ').at(-1)?.toLowerCase()||'__none__'));
 if(!((doi&&fraction>=.4)||(fraction>=.7&&author)))throw Error('article_identity_mismatch');
 if(pages.reduce((sum,p)=>sum+p.text.length,0)<2200)throw Error('not_full_article');
}
export {extract} from './oa-extract.ts';
import {extract} from './oa-extract.ts';
export async function fetchSource(paper:any,candidate:{url:string;kind:'pdf'|'html'},supplied?:Response,onStatus:(s:string)=>void=()=>{}):Promise<OAExtract>{
 const r=supplied||await fetch(candidate.url,{mode:'cors',credentials:'omit',signal:AbortSignal.timeout(12000)});
 if(!r.ok)throw Error('http_'+r.status);
 if(Number(r.headers.get('content-length')||0)>MAX_BYTES)throw Error('document_too_large');
 const reader=r.body?.getReader();if(!reader)throw Error('empty_document');
 let n=0;const chunks:Uint8Array[]=[];
 try{while(true){const {done,value}=await reader.read();if(done)break;n+=value.length;if(n>MAX_BYTES)throw Error('document_too_large');chunks.push(value);}}finally{await reader.cancel().catch(()=>{});}
 const all=new Uint8Array(n);let at=0;for(const c of chunks){all.set(c,at);at+=c.length;}
 const bytes=all.buffer;
 onStatus('3／5 已收到來源回應（'+n.toLocaleString()+' bytes）；正在檢查格式與論文身分…');
 let articleBytes=false;
 try{
 const source=supplied?decodeURIComponent(r.headers.get('X-Atlas-Source')||''):r.url||candidate.url;
 if(!safeURL(source))throw Error('untrusted_resolved_source');
 const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
 if(supplied&&(r.headers.get('X-Atlas-Hash')!==hash||r.headers.get('X-Atlas-DOI')!==paper.doi.toLowerCase()))throw Error('gateway_integrity_mismatch');
 const pdf=bytes.byteLength>=4&&new TextDecoder('ascii').decode(bytes.slice(0,4))==='%PDF';
 const ct=r.headers.get('content-type')||'';
 if(pdf&&!/application\/pdf|octet-stream/i.test(ct))throw Error('pdf_content_type_mismatch');
 articleBytes=pdf;
 const document=pdf?await pdfPages(bytes):{pages:/text\/html/i.test(ct)?htmlPages(new TextDecoder().decode(bytes)):[],total:0};
 const pages=document.pages;
 if(!pages.length)throw Error('not_pdf_or_article_html');
 articleBytes=true;
 validate(paper,pages);
 onStatus('4／5 論文身分已核對；正在搜尋假設、方法、結果、理論與穩健性證據…');
 const result=await extract(paper,pages,source,pdf?'pdf':'html');
 return {...result,downloaded:true,identity_verified:true,parsed_bytes:n,source_hash:hash,
  license:r.headers.get('X-Atlas-License')||'provider_oa_permission',source_version:r.headers.get('X-Atlas-Version')||'provider_version_unknown',
  total_pages:document.total||pages.length,partial:pdf&&document.total>MAX_PAGES};
 }catch(error){const e=error instanceof Error?error:new Error(String(error));Object.assign(e,{downloaded_bytes:articleBytes?n:0,response_bytes:n});throw e;}
}
export async function analyzeBrowserOA(paper:any,onStatus:(s:string)=>void):Promise<OAExtract>{
 const fail=(status:string,attempts:OAExtract['attempts'],oa:boolean,report:string):OAExtract=>({
   status,source_url:null,open_access:oa,pages:0,format:null,attempts,report,
   fields:Object.fromEntries(['sample_period','data_source','empirical_method'].map(k=>
     [k,{value:null,excerpt:null,page:null,status:'unknown'}])),
   hypotheses:[],findings:[],robustness:[],downloaded:false,identity_verified:false});
 if(!doiOk(paper.doi))return fail('invalid_doi',[],false,'無法確認為 SMJ DOI。');
 onStatus('1／5 正在向 OpenAlex 取得最新的 Open Access 全文來源…');
 const raw=await openAlexMetadata(paper.doi,paper.enrichment?.openalex_id);
 const sources=candidatesFor(paper,raw);
 const oa=sources.length>0||!!raw?.open_access?.is_oa;
 const attempts:OAExtract['attempts']=[],started=Date.now();
 let downloaded=0;
 onStatus('2／5 正在由受限 DOI 取件服務下載已授權 OA 原文…');
 try{
  const response=await fetch(GATEWAY,{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify({doi:paper.doi}),signal:AbortSignal.timeout(75000)});
  if(response.ok){
   const source=decodeURIComponent(response.headers.get('X-Atlas-Source')||'');
   const result=await fetchSource(paper,{url:source,kind:'pdf'},response,onStatus);
   onStatus('5／5 全文已解析；正在顯示逐欄來源證據。');
   return {...result,attempts:[{url:source,status:'downloaded_identity_verified_parsed_via_doi_gateway'}]};
  }
  const error=await response.json().catch(()=>({error:'http_'+response.status}));
  attempts.push(...(error.attempts||[]).map((a:any)=>({url:String(a.url),status:String(a.status)})));
  attempts.push({url:GATEWAY,status:'gateway_'+response.status+'_'+error.error});
  if(response.status===429)return fail('rate_limited',attempts,oa,'單篇／每小時取件預算已達上限，請稍後重新分析。');
 }catch(error){downloaded=Number((error as any)?.downloaded_bytes||0);attempts.push({url:GATEWAY,status:error instanceof Error?error.message:'gateway_unavailable'});}
 if(!sources.length)return fail('no_eligible_source',attempts,oa,'目前沒有受支援且權限足夠的 OA 來源；不是認定這篇論文沒有全文。');
 for(const item of sources){
   if(Date.now()-started>80000)break;
   onStatus('正在下載並檢查 OA 全文（'+(attempts.length+1)+'／'+sources.length+'）：'+new URL(item.url).hostname);
   try{
     const result=await fetchSource(paper,item,undefined,onStatus);
     return {...result,attempts:[...attempts,{url:item.url,status:'parsed'}]};
   }catch(e){
     downloaded=Math.max(downloaded,Number((e as any)?.downloaded_bytes||0));
     const text=e instanceof Error?e.message:'browser_fetch_failed';
     attempts.push({url:item.url,status:/Failed to fetch|NetworkError|Load failed/i.test(text)?
       'browser_cors_or_network_blocked':text.slice(0,100)});
   }
 }
 return {...fail(downloaded?'downloaded_not_parsed':'oa_fetch_blocked',attempts,oa,
   downloaded?'已收到原文位元組，但身分／格式／解析驗證未通過；不會標為全文分析成功。':'已嘗試受限取件服務與可用直接來源；存取、CORS、robots 或格式限制使本次未取得全文。這不表示文章不是 OA。'),downloaded:downloaded>0,parsed_bytes:downloaded};
}
