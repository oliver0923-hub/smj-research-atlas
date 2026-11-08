import test from 'node:test';
import assert from 'node:assert/strict';
import {makeHandler,validDOI,safeURL,candidates,robotsAllowed,publicIP,ORIGIN,QUOTA_SQL} from '../worker/index.js';
const DOI='10.1002/smj.3657';
const URL='https://www.econstor.eu/bitstream/10419/313808/1/SMJ_SMJ3657.pdf';
const location={is_oa:true,version:'submittedVersion',license:'cc-by-nc-nd',pdf_url:URL};
const request=(body={doi:DOI},origin=ORIGIN)=>new Request('https://gateway.test/api/document',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify(body)});
const db=()=>({prepare(sql){return {bind(...args){if(sql===QUOTA_SQL)return args;return {async first(){return null;},async run(){return {};}};}};},async batch(){return [{results:[{hits:1}]},{results:[{hits:1}]},{results:[{hits:1}]}];}});
function network(sourceResponse=()=>new Response('%PDF-real-test-bytes',{headers:{'Content-Type':'application/pdf'}})){
 const called=[];
 const fetch=async(url,options)=>{
  called.push(url);assert.equal(options.redirect,'manual');
  if(url.includes('/data/papers/'))return Response.json({paper_id:'doi:'+DOI,doi:DOI,title:'A real article',authors:['Author']});
  if(url.includes('api.openalex.org'))return Response.json({doi:'https://doi.org/'+DOI,locations:[location]});
  if(url.includes('dns-query'))return Response.json({Answer:[{type:1,data:'93.184.216.34'}]});
  if(url.endsWith('/robots.txt'))return new Response('User-agent: *\nDisallow: /private/\n');
  return sourceResponse();
 };
 return {fetch,called};
}
test('DOI-only, exact trusted host and private address guards',()=>{
 assert.ok(validDOI(DOI));assert.ok(!validDOI(DOI+'?url=https://localhost'));
 for(const u of ['http://www.econstor.eu/a','https://www.econstor.eu.evil.test/a','https://user@www.econstor.eu/a','https://127.0.0.1/a','https://[::1]/a','https://www.econstor.eu:444/a'])assert.throws(()=>safeURL(u));
 for(const ip of ['10.0.0.1','127.0.0.1','169.254.169.254','172.31.0.1','192.168.0.1','100.64.0.1','::1','fd00::1','2001:db8::1'])assert.equal(publicIP(ip),false);
 assert.ok(publicIP('93.184.216.34'));
});
test('explicitly licensed repository source is not lost to an incomplete version label',()=>{
 assert.equal(candidates({locations:[location]})[0].version,'submittedVersion');
 assert.equal(candidates({locations:[{...location,license:null}]}).length,0);
 assert.equal(candidates({locations:[{...location,is_oa:false}]}).length,0);
});
test('robots specificity, allow exceptions, own user-agent and wildcard',()=>{
 assert.equal(robotsAllowed('User-agent: *\nDisallow: /a\nAllow: /a/public','/a/public/file'),true);
 assert.equal(robotsAllowed('User-agent: *\nDisallow: /*.pdf$','/a.pdf'),false);
 assert.equal(robotsAllowed('User-agent: otherbot\nDisallow: /\nUser-agent: *\nDisallow: /secret','/a'),true);
 assert.equal(robotsAllowed('User-agent: SMJResearchAtlas\nDisallow: /\nUser-agent: *\nAllow: /','/a'),false);
});
test('real byte transport, source attribution, no cache and limited CORS',async()=>{
 const n=network(),handle=makeHandler(n.fetch,async()=>{});
 const result=await handle(request(),{DB:db()});assert.equal(result.status,200);
 assert.equal(await result.text(),'%PDF-real-test-bytes');
 assert.equal(result.headers.get('X-Atlas-DOI'),DOI);
 assert.equal(decodeURIComponent(result.headers.get('X-Atlas-Source')),URL);
 assert.equal(result.headers.get('Cache-Control'),'no-store');
 assert.match(result.headers.get('X-Atlas-Hash'),/^[a-f0-9]{64}$/);
 assert.equal(result.headers.get('Access-Control-Allow-Origin'),ORIGIN);
 assert.ok(n.called.includes(URL));
});
test('redirect to metadata/private/unlisted host is stopped before retrieval',async()=>{
 const n=network(()=>new Response(null,{status:302,headers:{location:'http://169.254.169.254/secrets'}}));
 const r=await makeHandler(n.fetch,async()=>{})(request(),{DB:db()});
 assert.equal(r.status,422);assert.equal(n.called.some(u=>u.includes('169.254')),false);
 assert.equal((await r.json()).downloaded,false);
});
test('forbidden origins, caller URLs and oversized requests never reach upstream',async()=>{
 let calls=0;const h=makeHandler(async()=>{calls++;throw Error('must not fetch');});
 assert.equal((await h(request({},'https://attacker.test'),{DB:db()})).status,403);
 assert.equal((await h(request({doi:DOI,url:URL}),{DB:db()})).status,422);
 assert.equal((await h(request({doi:'x'.repeat(200)}),{DB:db()})).status,413);
 assert.equal(calls,0);
});
test('quota fails closed; exhausted and missing stores never retrieve documents',async()=>{
 let calls=0;const h=makeHandler(async()=>{calls++;});
 assert.equal((await h(request(),{})).status,503);
 const DB={prepare(){return {bind(){return {};}};},async batch(){return [{results:[]}];}};
 assert.equal((await h(request(),{DB})).status,429);assert.equal(calls,0);
});
test('403 is access denial, not a parser success or a claim of paywall',async()=>{
 const n=network(()=>new Response(null,{status:403}));
 const r=await makeHandler(n.fetch,async()=>{})(request(),{DB:db()});
 const d=await r.json();assert.equal(d.downloaded,false);assert.equal(d.parsed,false);
 assert.equal(d.attempts[0].status,'http_403');
});
test('SSRF public DNS check rejects private final addresses',async()=>{
 const n=network();const f=async(u,o)=>u.includes('dns-query')?Response.json({Answer:[{type:1,data:'10.0.0.2'}]}):n.fetch(u,o);
 const r=await makeHandler(f,async()=>{})(request(),{DB:db()});
 assert.equal((await r.json()).attempts[0].status,'nonpublic_dns');
 assert.equal(n.called.includes(URL),false);
});
test('Content-Type/magic and declared-size mismatch are rejected',async()=>{
 for(const response of [()=>new Response('not pdf',{headers:{'Content-Type':'application/pdf'}}),()=>new Response('%PDF-big',{headers:{'Content-Type':'application/pdf','Content-Length':'30000000'}})]){
  const n=network(response),r=await makeHandler(n.fetch,async()=>{})(request(),{DB:db()});
  assert.equal(r.status,422);assert.equal((await r.json()).downloaded,false);
 }
});
test('HTTP 200 bot challenges are not transported as full text',async()=>{
 const n=network(()=>new Response('<html><title>Making sure you are not a bot!</title></html>',{headers:{'Content-Type':'text/html'}}));
 const r=await makeHandler(n.fetch,async()=>{})(request(),{DB:db()});
 assert.equal(r.status,422);assert.equal((await r.json()).attempts[0].status,'bot_challenge_html');
});
test('deposited item uses DOI-checked DSpace ORIGINAL HAL links, not guessed PDF names',async()=>{
 const calls=[];
 const f=async(u,o)=>{
  calls.push(u);
  if(u.includes('/data/papers/'))return Response.json({paper_id:'doi:'+DOI,doi:DOI,title:'Test study',authors:['Author']});
  if(u.includes('api.openalex.org'))return Response.json({doi:'https://doi.org/'+DOI,locations:[{id:'pmh:oai:repositorio.ie.edu:20.500.14417/4179',is_oa:true,license:'cc-by-nc-nd',version:'submittedVersion'}]});
  if(u.includes('dns-query'))return Response.json({Answer:[{type:1,data:'93.184.216.34'}]});
  if(u.endsWith('/robots.txt'))return new Response('User-agent: *\nAllow: /');
  if(u.includes('/pid/find'))return new Response(null,{status:302,headers:{location:'https://repositorio.ie.edu/server/api/core/items/item1'}});
  if(u.endsWith('/items/item1'))return Response.json({metadata:{'dc.identifier.doi':[{value:'https://doi.org/'+DOI}],'dc.rights.accessRights':[{value:'openAccess'}]},_links:{bundles:{href:'https://repositorio.ie.edu/server/api/core/items/item1/bundles'}}});
  if(u.endsWith('/bundles'))return Response.json({_embedded:{bundles:[{name:'ORIGINAL',_links:{bitstreams:{href:'https://repositorio.ie.edu/server/api/core/bundles/b1/bitstreams'}}}]}});
  if(u.endsWith('/bitstreams'))return Response.json({_embedded:{bitstreams:[{name:'paper.pdf',sizeBytes:2000,_links:{content:{href:'https://repositorio.ie.edu/server/api/core/bitstreams/file1/content'}}}]}});
  if(u.endsWith('/content'))return new Response('%PDF-from-deposited-original',{headers:{'Content-Type':'application/pdf'}});
  throw Error('Unexpected URL '+u);
 };
 const r=await makeHandler(f,async()=>{})(request(),{DB:db()});
 assert.equal(r.status,200);assert.equal(await r.text(),'%PDF-from-deposited-original');
 assert.ok(calls.some(x=>x.includes('id=hdl%3A20.500.14417%2F4179')));
});
test('429 Retry-After persists across requests instead of repeatedly contacting the host',async()=>{
 const backoffs=new Map(),DB=db();
 const original=DB.prepare;
 DB.prepare=sql=>({bind(...args){
  if(sql===QUOTA_SQL)return original(sql).bind(...args);
  if(sql.startsWith('SELECT'))return {async first(){return backoffs.has(args[0])?{expires_at:backoffs.get(args[0])}:null;}};
  return {async run(){backoffs.set(args[0],args[1]);}};
 }});
 const n=network(()=>new Response(null,{status:429,headers:{'Retry-After':'7200'}}));
 const handler=makeHandler(n.fetch,async()=>{});
 const first=await handler(request(),{DB});assert.equal(first.status,422);
 const count=n.called.filter(x=>x===URL).length;
 const second=await handler(request(),{DB});assert.equal(second.status,422);
 assert.equal(n.called.filter(x=>x===URL).length,count);
 assert.ok(backoffs.get('backoff:www.econstor.eu')>Date.now()/1000+7100);
});
