import type {Page,OAExtract,Evidence} from './browser-oa';
type Segment={page:number;text:string;section:string;start:number;end:number};
const tidy=(s:string)=>s.replace(/\s+/g,' ').trim();
const HEADER=/^(?:\d+(?:\.\d+)*[. |–-]*)?(abstract|(?:research|managerial) summary|introduction|literature review|hypothes(?:is|es)(?: development)?|theoretical (?:background|development|framework)|research (?:design|methods?)|empirical (?:setting(?: and data)?|strategy|results?|analysis)|methodology|methods?|data(?: and (?:methods|sample))?|sample|measures?|measurement|results?|discussion|robustness(?: checks)?|sensitivity(?: analysis)?|conclusions?|references|bibliography|appendi\w*.*|supporting information)\s*[:.]?$/i;
export function segments(pages:Page[]){
 const out:Segment[]=[];let section='unknown';
 for(const page of pages){
  let pending='';const normalized=tidy(page.text);
  function flush(){
   if(!pending)return;
   const parts=pending.split(/(?<=[.!?])\s+(?=[A-Z])/);
   for(let i=0;i<parts.length-1;i++)if(/^(?:Hypothesis|Proposition)\s*\(?[HP]?\d+[a-z]?\)?\.$/i.test(parts[i]))parts.splice(i,2,parts[i]+' '+parts[i+1]);
   if(!/^(references|bibliography)/i.test(section))for(const text of parts){
    if(text.length<25)continue;
    const start=normalized.indexOf(text);out.push({page:page.page,text,section,start,end:start+text.length});
   }
   pending='';
  }
  for(const line of page.text.split(/\n+/).map(tidy).filter(Boolean)){
   if(line.length<120&&HEADER.test(line)){flush();section=line.toLowerCase();continue;}
   if(/^Hypothesis\s*(?:\(?H?)?\d|^Proposition\s*(?:\(?P?)?\d|^H\d+[a-z]?\s*:/i.test(line))flush();
   pending=tidy(pending+' '+line);
   if(/[.!?][”'"\])]*$/.test(line)&&!/^Hypothesis\s*\(?H?\d+[a-z]?\)?\s*\.$/i.test(pending)||pending.length>2200)flush();
  }
  flush();
 }
 return out;
}
const DATA=/\b(Longitudinal Business Database|Business Dynamics Statistics|American Community Survey|Census Bureau|PatentsView|VentureXpert|Compustat|ExecuComp|BoardEx|CRSP|Orbis|FactSet|Factiva|FAME|Worldscope|ASSET4|Thomson Reuters|Institutional Shareholder Services|ISS|NBER|USPTO|PATSTAT|SDC(?: Platinum)?|KLIPS|IMDb)\b/gi;
const METHODS=/\b(negative binomial|Poisson|fixed[- ]effects?(?: regressions?)?|ordinary least squares|OLS(?: regressions?)?|logistic regression|logit|panel regression|generalized estimating equations|instrumental variables?|difference[- ]in[- ]differences|event study|random[- ]effects?|Tobit(?: regression)?|probit(?: regression)?|two[- ]stage least squares|2SLS|Cox proportional hazards?|qualitative comparative analysis|hierarchical regression|temporal bracketing|multiple case study)\b/gi;
const THEORIES=/\b(upper echelons theory|agency theor(?:y|ies)|resource dependence theor(?:y|ies)|resource[- ]based view|attention[- ]based view|behavioral theory of the firm|transaction cost (?:economics|theory)|institutional theory|social exchange theory|dynamic capabilities(?: theory| view)?|social identity theory|information processing theory)\b/gi;
const escape=(s:string)=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
export async function extract(paper:any,pages:Page[],source_url:string,format:'pdf'|'html'):Promise<OAExtract>{
 const rows=segments(pages);
 async function evidence(s:Segment,kind:string,label:string,focus=''):Promise<Evidence>{
  const tokens=s.text.split(/\s+/);const focusAt=focus?s.text.toLowerCase().indexOf(focus.toLowerCase()):-1;
  const start=focusAt>=0?Math.max(0,s.text.slice(0,focusAt).trim().split(/\s+/).length-3):0;
  const quote=tokens.slice(start,start+24);
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s.text)))].map(x=>x.toString(16).padStart(2,'0')).join('');
  return {page:s.page,section:s.section,kind,label,excerpt:quote.join(' '),span_hash:hash,
   offset_start:s.start,offset_end:s.end,confidence:'rule_based_uncalibrated'};
 }
 const values:Record<string,Array<{value:string;segment:Segment}>>={sample_period:[],data_source:[],empirical_method:[]};
 const hypotheses:Evidence[]=[],findings:Evidence[]=[],robustness:Evidence[]=[],theories:Evidence[]=[],constructs:Evidence[]=[];
 const seen=new Set<string>();
 for(const s of rows){
  const text=s.text;
  const own=/\b(?:we|our|sample|data(?:set|base)?s?|estimat\w*|collected|obtained|drawn|employ\w*)\b/i.test(text);
  const methodSection=/method|measure|data|sample|research design|empirical strategy|appendi|robustness/i.test(s.section);
  if(own&&(methodSection||/\b(?:we|our|the final) (?:use|employ|estimate|sample|data|collected)\b/i.test(text))){
   for(const match of text.matchAll(/\b((?:19|20)\d{2})\s*(?:[-–—‐‑]|to|through|and)\s*((?:19|20)\d{2})\b/g)){
    const before=text.slice(Math.max(0,match.index!-140),match.index);
    const treatment=/treatments?|enactment|legislation|reforms?/i.test(before)&&!/sample|underlying data|data (?:cover|span)/i.test(before);
    if(!treatment&&/sample|data|period|panel|observations|study covers/i.test(text)&&+match[2]>=+match[1]&&+match[2]-+match[1]<=70)
     values.sample_period.push({value:match[1]+'–'+match[2],segment:s});
   }
   for(const match of text.matchAll(DATA)){
    if(match[0].toLowerCase()==='iss'&&match[0]!=='ISS')continue;
    values.data_source.push({value:match[0],segment:s});
   }
   for(const match of text.matchAll(METHODS)){
    if(/discussion|conclusion|limitations/i.test(s.section))continue;
    if(/robustness|sensitivity|alternative specification|placebo|subsample/i.test(text))continue;
    if(/(?:rather than|instead of|do not use|not use)\s*$/i.test(text.slice(Math.max(0,match.index!-45),match.index)))continue;
    values.empirical_method.push({value:match[0],segment:s});
   }
  }
  const h=text.match(/^\s*(?:Hypothesis\s*\(?H?\s*|H)(\d+[a-z]?)\s*\)?\s*[:.)-]\s*\S/i);
  const p=text.match(/^\s*(?:Proposition\s*\(?P?\s*|P)(\d+[a-z]?)\s*\)?\s*[:.)-]\s*\S/i);
  if((h||p)&&hypotheses.length<12){
   const label=(h?'H':'P')+(h||p)![1];
   if(!seen.has(label)){seen.add(label);hypotheses.push(await evidence(s,h?'proposed_hypothesis':'proposed_proposition',label));}
  }
  const result=/\b(?:we (?:further |also )?(?:find|found|demonstrate|show|report)|our (?:findings|results) (?:show|suggest|indicate)|results (?:show|suggest|indicate)|we find support)\b/i.test(text)||
   /\b(?:hypothesis|H)\s*\d+[a-z]?\b.{0,100}\b(?:supported|confirmed|not supported)\b/i.test(text);
  if(result&&findings.length<12){
   const labels=[...text.matchAll(/\b(?:Hypothesis\s*\(?H?\s*|H)(\d+[a-z]?)\b/gi)].map(m=>'H'+m[1]);
   const item=await evidence(s,'finding',labels.length===1?labels[0]:'作者發現句');
   item.support_status=labels.length!==1?'unknown':/not support|no support|not confirmed|fail\w* to support/i.test(text)?'not_supported':/partial\w* support/i.test(text)?'partially_supported':/support|confirm/i.test(text)?'supported':'unknown';
   item.significance=/not (?:statistically )?significant|insignificant|non[- ]significant/i.test(text)?'not_significant':/statistically significant|\bp\s*[<≤]\s*0?\.0[015]/i.test(text)?'significant':'unknown';
   findings.push(item);
  }
  if(/robustness|sensitivity|alternative (?:measures|specifications)|placebo|endogeneity|subsample/i.test(text)&&/we|our|conduct|perform|estimate|test|results|analysis/i.test(text)&&robustness.length<12)
   robustness.push(await evidence(s,/sensitivity/i.test(text)?'sensitivity':'robustness','作者檢驗程序；未推定通過'));
  for(const m of text.matchAll(THEORIES)){
   const authorUse=/\b(?:we (?:draw|build|use|adopt|apply|integrate)|drawing on|building on|grounded in)\b/i.test(text);
   const id=m[0].toLowerCase()+'|'+authorUse;if(seen.has(id)||theories.length>=12)continue;seen.add(id);
   theories.push(await evidence(s,authorUse?'author_use_statement':'theory_mention',m[0]));
  }
  for(const m of text.matchAll(/\bwe (?:measured?|defined?|operationalized?|calculated?|coded?)\s+([a-z][a-z /()-]{2,65}?)\s+(?:as|using|by)\b/gi)){
   if(/^(?:its|their|the following|following|a |an )\b/i.test(m[1]))continue;
   const id='construct|'+m[1].toLowerCase();if(seen.has(id)||constructs.length>=12)continue;seen.add(id);
   constructs.push(await evidence(s,'explicit_operational_construct',m[1]));
  }
 }
 const fields:OAExtract['fields']={};
 for(const [key,all] of Object.entries(values)){
  const chosen=[...new Map(all.map(x=>[x.value.toLowerCase().replace(/-/g,' '),x])).values()].slice(0,8);
  const unique=chosen.map(x=>x.value);
  const proofs:Evidence[]=[];for(const row of chosen)proofs.push(await evidence(row.segment,'field_evidence',row.value,row.value));
  const conflict=key==='sample_period'&&unique.length>1;
  fields[key]={value:unique.length&&!conflict?unique.join(', '):null,status:conflict?'evidence_conflict':unique.length?'source_grounded_lexical':'unknown',
   reason:conflict?'不同原文期間／樣本規格尚未可靠對應':unique.length?'原文明示詞組，未校準語義正確率':'not_found_after_scan',
   page:proofs[0]?.page||null,excerpt:proofs[0]?.excerpt||null,evidence:proofs};
 }
 return {status:'parsed',source_url,open_access:true,pages:pages.length,format,attempts:[],fields,hypotheses,findings,robustness,theories,constructs,
  report:'已解析實際下載的原文；搜尋包含可讀的表格文字與附錄。影像公式、複雜表格結構及語義關係未全面辨識，無證據者維持未知。'};
}
