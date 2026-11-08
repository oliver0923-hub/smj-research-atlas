/** DOI-only transient licensed-OA retrieval. No arbitrary URL or PDF persistence. */
export const ATLAS='https://oliver0923-hub.github.io/smj-research-atlas';
export const ORIGIN='https://oliver0923-hub.github.io';
const ORIGINS=new Set([ORIGIN,'http://127.0.0.1:4321','http://localhost:4321']);
export const MAX_BYTES=22_000_000;
const UA='SMJResearchAtlas/5.1 (+https://github.com/oliver0923-hub/smj-research-atlas; OA research)';
const HOSTS=new Set(['www.econstor.eu','econstor.eu','repositorio.ie.edu','lbsresearch.london.edu','openaccess.city.ac.uk',
 'ora.ox.ac.uk','research-repository.st-andrews.ac.uk','onlinelibrary.wiley.com','sms.onlinelibrary.wiley.com']);
const LICENSE=/^(?:cc-by(?:-sa|-nc|-nd|-nc-sa|-nc-nd)?|cc0|public-domain)$/i;
const encoder=new TextEncoder();
const digest=async x=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',typeof x==='string'?encoder.encode(x):x))].map(v=>v.toString(16).padStart(2,'0')).join('');
export function validDOI(s){return typeof s==='string'&&/^10\.1002\/smj\.\d+[a-z0-9-]*$/i.test(s)&&s.length<=90;}
export function safeURL(raw){
 const u=new URL(raw);
 if(u.protocol!=='https:'||u.username||u.password||u.port||!HOSTS.has(u.hostname)||raw.length>2048)throw Error('source_host_not_allowed');
 return u;
}
export function candidates(raw){
 const urls=new Map();
 for(const l of [...(raw.locations||[]),raw.best_oa_location,raw.primary_location]){
  if(!l?.is_oa||!LICENSE.test(l.license||''))continue;
  // Explicit CC repository permissions can be legitimate even when provider version labels are incomplete.
  for(const k of ['pdf_url','landing_page_url']){
   if(!l[k])continue;
   try{const u=safeURL(l[k]);urls.set(u.href,{url:u.href,license:l.license,version:l.version||'unknown',kind:k});}catch{}
  }
 }
 return [...urls.values()].sort((a,b)=>Number(/wiley\.com$/.test(new URL(a.url).hostname))-Number(/wiley\.com$/.test(new URL(b.url).hostname))||Number(a.kind!=='pdf_url')-Number(b.kind!=='pdf_url')).slice(0,6);
}
export function publicIP(ip){
 if(ip.includes(':'))return /^[23][0-9a-f]{0,3}:/i.test(ip)&&!ip.toLowerCase().startsWith('2001:db8:');
 const a=ip.split('.').map(Number);
 return a.length===4&&a.every(n=>Number.isInteger(n)&&n>=0&&n<=255)&&a[0]!==0&&a[0]!==10&&a[0]!==127&&a[0]<224&&
  !(a[0]===169&&a[1]===254)&&!(a[0]===172&&a[1]>=16&&a[1]<=31)&&!(a[0]===192&&[0,168].includes(a[1]))&&
  !(a[0]===100&&a[1]>=64&&a[1]<=127)&&!(a[0]===198&&[18,19,51].includes(a[1]))&&!(a[0]===203&&a[1]===0);
}
export function robotsAllowed(text,path){
 const groups=[];let group={agents:[],rules:[]},rulesStarted=false;
 for(const line of text.split(/\r?\n/)){
  const m=line.replace(/#.*/,'').trim().match(/^([^:]+):\s*(.*)$/);if(!m)continue;
  const k=m[1].trim().toLowerCase(),value=m[2].trim();
  if(k==='user-agent'){
   if(rulesStarted){groups.push(group);group={agents:[],rules:[]};rulesStarted=false;}
   if(value)group.agents.push(value.toLowerCase());
  }else if(['allow','disallow'].includes(k)&&group.agents.length){rulesStarted=true;if(value)group.rules.push({allow:k==='allow',path:value});}
 }
 groups.push(group);
 const own=groups.filter(g=>g.agents.some(a=>a!=='*'&&UA.toLowerCase().includes(a)));
 const selected=own.length?own:groups.filter(g=>g.agents.includes('*'));let best=null;
 for(const g of selected)for(const r of g.rules){
  const pattern=r.path.split('*').map(s=>s.replace(/[.+?^{}()|[\]\\]/g,'\\$&')).join('.*').replace(/\$$/,'$');
  if(new RegExp('^'+pattern).test(path)&&(!best||r.path.length>best.path.length||r.path.length===best.path.length&&r.allow))best=r;
 }
 return best?best.allow:true;
}
async function bounded(response,max){
 if(Number(response.headers.get('content-length')||0)>max){await response.body?.cancel();throw Error('document_too_large');}
 const reader=response.body?.getReader();if(!reader)throw Error('empty_response');
 const parts=[];let n=0;
 try{while(true){const {done,value}=await reader.read();if(done)break;n+=value.length;if(n>max)throw Error('document_too_large');parts.push(value);}}
 finally{await reader.cancel().catch(()=>{});}
 const bytes=new Uint8Array(n);let offset=0;for(const p of parts){bytes.set(p,offset);offset+=p.length;}return bytes;
}
function headers(origin){return {'Access-Control-Allow-Origin':origin,'Vary':'Origin','Cache-Control':'no-store',
 'Access-Control-Expose-Headers':'X-Atlas-DOI,X-Atlas-Source,X-Atlas-License,X-Atlas-Version,X-Atlas-Hash,X-Atlas-Bytes,X-Atlas-Attempts',
 'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'};}
const json=(body,status=200,extra={})=>new Response(JSON.stringify(body),{status,headers:{...headers(ORIGIN),'Content-Type':'application/json',...extra}});
export const QUOTA_SQL=`INSERT INTO quotas(bucket,hits,expires_at) VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET hits=quotas.hits+1 WHERE quotas.hits<? RETURNING hits`;
async function quota(env,ip,doi){
 if(!env.DB)throw Error('quota_store_unavailable');
 const now=Math.floor(Date.now()/1000),hour=Math.floor(now/3600),day=Math.floor(now/86400);
 const hashed=(await digest(ip)).slice(0,24);
 const specs=[[`day:${day}`,now+86400,100],[`ip:${hour}:${hashed}`,now+3600,12],[`doi:${hour}:${doi}`,now+3600,8]];
 const results=await env.DB.batch(specs.map(([k,expires,cap])=>env.DB.prepare(QUOTA_SQL).bind(k,expires,cap)));
 return results.every(r=>r.results?.length===1);
}
export function makeHandler(fetchImpl=fetch,wait=ms=>new Promise(r=>setTimeout(r,ms))){
 return async function handle(request,env){
  const url=new URL(request.url);
  const origin=request.headers.get('Origin')||ORIGIN;
  const reply=(body,status=200,extra={})=>json(body,status,{...headers(origin),...extra});
  if(request.method==='GET'&&url.pathname==='/api/health')return reply({status:'ok',service:'smj-doi-oa-gateway',version:'1.2.0',quotas:!!env.DB});
  if(url.pathname!=='/api/document')return reply({error:'not_found'},404);
  if(!ORIGINS.has(request.headers.get('Origin')))return json({error:'site_origin_required'},403);
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{...headers(origin),'Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'content-type'}});
  if(request.method!=='POST')return reply({error:'post_required'},405);
  if(!request.headers.get('content-type')?.startsWith('application/json'))return reply({error:'json_required'},415);
  let body;try{body=new TextDecoder().decode(await bounded(request,180));}catch{return reply({error:'request_too_large'},413);}
  let input;try{input=JSON.parse(body);}catch{return reply({error:'invalid_json'},400);}
  if(Object.keys(input||{}).join(',')!=='doi'||!validDOI(input.doi))return reply({error:'indexed_smj_doi_only'},422);
  const doi=input.doi.toLowerCase();
  try{if(!await quota(env,request.headers.get('CF-Connecting-IP')||'unknown',doi))return reply({error:'rate_limited'},429,{'Retry-After':'3600'});}
  catch{return reply({error:'quota_store_unavailable'},503);}
  let requests=0;const started=Date.now(),hostTimes=new Map();
  async function get(u,max=3_000_000,accept='application/json'){
   if(++requests>24||Date.now()-started>65000)throw Error('request_budget');
   const host=new URL(u).hostname,now=Math.floor(Date.now()/1000);
   const backoff=await env.DB.prepare('SELECT expires_at FROM quotas WHERE bucket=?').bind('backoff:'+host).first();
   if(backoff?.expires_at>now)throw Error('host_retry_after_'+(backoff.expires_at-now));
   if(HOSTS.has(host)&&hostTimes.has(host))await wait(Math.max(0,1000-(Date.now()-hostTimes.get(host))));
   hostTimes.set(host,Date.now());
   const response=await fetchImpl(u,{redirect:'manual',signal:AbortSignal.timeout(12000),headers:{'User-Agent':UA,'Accept':accept},credentials:'omit'});
   if(response.status===429){
    const value=response.headers.get('Retry-After');
    const seconds=Math.max(1,Math.min(86400,/^\d+$/.test(value||'')?Number(value):value?Math.ceil((Date.parse(value)-Date.now())/1000)||3600:3600));
    await env.DB.prepare('INSERT INTO quotas(bucket,hits,expires_at) VALUES(?,0,?) ON CONFLICT(bucket) DO UPDATE SET expires_at=MAX(quotas.expires_at,excluded.expires_at)').bind('backoff:'+host,now+seconds).run();
   }
   return {response,bytes:response.ok?await bounded(response,max):null};
  }
  const attempts=[];
  try{
   const h=(await digest('doi:'+doi)).slice(0,16);
   const identity=await get(ATLAS+'/data/papers/'+h+'.json');
   if(identity.response.status!==200)return reply({error:'not_indexed',doi},404);
   const paper=JSON.parse(new TextDecoder().decode(identity.bytes));
   if(paper.paper_id!=='doi:'+doi||paper.doi?.toLowerCase()!==doi||!paper.title||!paper.authors?.length)throw Error('atlas_identity_mismatch');
   const metadata=await get('https://api.openalex.org/works/https://doi.org/'+doi+'?select=doi,locations,best_oa_location,primary_location');
   if(metadata.response.status!==200)return reply({error:'openalex_http_'+metadata.response.status,doi},502);
   const raw=JSON.parse(new TextDecoder().decode(metadata.bytes));
   if(raw.doi?.toLowerCase()!=='https://doi.org/'+doi)throw Error('openalex_doi_mismatch');
   const options=candidates(raw),robots=new Map(),dns=new Set(),cooldowns=new Set();
   async function inspect(rawURL){
    const u=safeURL(rawURL);
    if(cooldowns.has(u.hostname))throw Error('host_retry_after');
    if(!dns.has(u.hostname)){
     for(const type of ['A','AAAA']){
      const d=await get('https://cloudflare-dns.com/dns-query?name='+encodeURIComponent(u.hostname)+'&type='+type,64000,'application/dns-json');
      if(!d.response.ok)throw Error('dns_check_unavailable');
      const answers=JSON.parse(new TextDecoder().decode(d.bytes));
      if((answers.Answer||[]).some(x=>[1,28].includes(x.type)&&!publicIP(x.data)))throw Error('nonpublic_dns');
     }
     dns.add(u.hostname);
    }
    if(!robots.has(u.origin)){
     const r=await get(u.origin+'/robots.txt',100000,'text/plain');
     if(r.response.status===404)robots.set(u.origin,'');
     else if(r.response.ok)robots.set(u.origin,new TextDecoder().decode(r.bytes));
     else throw Error('robots_http_'+r.response.status);
     await wait(750);
    }
    if(!robotsAllowed(robots.get(u.origin),u.pathname+u.search))throw Error('robots_disallowed');
    return u;
   }
   async function repositoryJSON(start){
    let current=start;
    for(let i=0;i<4;i++){
     const u=await inspect(current),result=await get(u.href);
     if([301,302,303,307,308].includes(result.response.status)){
      current=safeURL(new URL(result.response.headers.get('location')||'',u).href).href;continue;
     }
     if(!result.response.ok||!result.response.headers.get('content-type')?.includes('json'))throw Error('repository_metadata_http_'+result.response.status);
     return JSON.parse(new TextDecoder().decode(result.bytes));
    }
    throw Error('repository_redirect_limit');
   }
   // Resolve the provider's deposited item ID using documented DSpace HAL links.
   // No DOI-specific PDF filename, guessed download URL or caller URL is accepted.
   for(const l of (raw.locations||[])){
    const handle=l.id?.match(/^pmh:oai:repositorio\.ie\.edu:(\d+(?:\.\d+)*\/\d+)$/)?.[1];
    if(!handle||!l.is_oa||!LICENSE.test(l.license||''))continue;
    try{
     const item=await repositoryJSON('https://repositorio.ie.edu/server/api/pid/find?id='+encodeURIComponent('hdl:'+handle));
     const ids=item.metadata?.['dc.identifier.doi']||[],rights=item.metadata?.['dc.rights.accessRights']||[];
     if(!ids.some(x=>x.value?.toLowerCase()==='https://doi.org/'+doi)||!rights.some(x=>/openAccess/i.test(x.value)))throw Error('repository_identity_or_rights_mismatch');
     const bundles=await repositoryJSON(item._links.bundles.href);
     const original=bundles._embedded?.bundles?.find(x=>x.name==='ORIGINAL');
     if(!original)throw Error('repository_no_original_bundle');
     const streams=await repositoryJSON(original._links.bitstreams.href);
     for(const bit of (streams._embedded?.bitstreams||[]).filter(x=>/\.pdf$/i.test(x.name)&&x.sizeBytes<=MAX_BYTES).slice(0,2)){
      const url=safeURL(bit._links.content.href).href;
      options.unshift({url,license:l.license,version:l.version||'unknown',kind:'pdf_url'});
     }
    }catch(e){attempts.push({url:'https://repositorio.ie.edu/handle/'+handle,status:String(e.message).slice(0,120)});}
    break;
   }
   if(!options.length)return reply({error:'no_eligible_licensed_source',doi,source_found:false,downloaded:false,parsed:false,attempts},404);
   for(const option of options.slice(0,6)){
    try{
     let current=option.url;let result;
     for(let n=0;n<5;n++){
      const u=await inspect(current);
      result=await get(u.href,MAX_BYTES,'application/pdf,text/html;q=0.9');
      if([301,302,303,307,308].includes(result.response.status)){
       const next=result.response.headers.get('location');if(!next)throw Error('redirect_without_location');
       current=safeURL(new URL(next,u).href).href;await wait(750);continue;
      }
      if(result.response.status===429){cooldowns.add(u.hostname);throw Error('http_429_retry_after_'+(result.response.headers.get('Retry-After')||'unknown'));}
      if(result.response.status!==200)throw Error('http_'+result.response.status);
      const magic=new TextDecoder().decode(result.bytes.slice(0,5)),ct=result.response.headers.get('content-type')||'';
      if(!(magic==='%PDF-'&&/application\/pdf|octet-stream/i.test(ct))&&!/text\/html/i.test(ct))throw Error('not_pdf_or_html');
      if(magic!=='%PDF-'){
       const html=new TextDecoder().decode(result.bytes);
       if(/making sure you|anubis|captcha|cf-chl-|verify.{0,20}human|access denied/i.test(html))throw Error('bot_challenge_html');
       if(!/<(?:article|main)\b/i.test(html)||!/<h[234][^>]*>[^<]*(?:methods?|data|theor|hypoth|measur)/i.test(html)||!/<h[234][^>]*>[^<]*(?:results?|discussion|conclusion|appendi)/i.test(html))throw Error('metadata_landing_not_fulltext');
      }
      // No raw document is stored or cached. Browser verifies content identity and parses the original bytes.
      return new Response(result.bytes,{headers:{...headers(origin),'Content-Type':magic==='%PDF-'?'application/pdf':'text/html',
       'X-Atlas-DOI':doi,'X-Atlas-Source':encodeURIComponent(current),'X-Atlas-License':option.license,'X-Atlas-Version':option.version,
       'X-Atlas-Hash':await digest(result.bytes),'X-Atlas-Bytes':String(result.bytes.length),'X-Atlas-Attempts':String(attempts.length+1)}});
     }
     throw Error('redirect_limit');
    }catch(e){attempts.push({url:option.url,status:String(e.message).slice(0,120)});}
   }
   return reply({error:'oa_sources_inaccessible',doi,source_found:true,downloaded:false,parsed:false,attempts},422);
  }catch(e){return reply({error:String(e.message).slice(0,100),doi,source_found:attempts.length>0,downloaded:false,parsed:false,attempts},502);}
 };
}
export default {fetch(request,env){return makeHandler()(request,env);}};
