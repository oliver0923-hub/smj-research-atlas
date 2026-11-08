import Fuse from 'fuse.js';
const app=document.getElementById('research-app')!;
const base=import.meta.env.BASE_URL;
const params=new URLSearchParams(location.search);
const labels:Record<string,string>={E0_metadata:'E0 書目',E1_abstract:'E1 摘要',E2_fulltext_section:'E2 正文章節',E3_measurement_text:'E3 衡量文字',validated_automatic:'自動來源一致性通過',provisional:'暫定推論',failed:'檢查失敗',insufficient_evidence:'證據不足',unknown:'未知',independent:'IV',dependent:'DV',mediator:'中介',moderator:'調節',control:'控制',instrument:'工具變數'};
const e=(tag:string,text?:any,cls?:string)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n};
const add=(parent:Element,tag:string,text?:any,cls?:string)=>{const n=e(tag,text,cls);parent.append(n);return n};
const link=(parent:Element,text:string,url:string)=>{const n=add(parent,'a',text) as HTMLAnchorElement;n.href=url;return n};
const get=async(name:string)=>{const r=await fetch(base+'data/'+name+'.json');if(!r.ok)throw Error(name+' HTTP '+r.status);return r.json()};
const title=(t:string,lead:string)=>{app.replaceChildren();add(app,'div','SMJ RESEARCH INTELLIGENCE · v4','eyebrow');add(app,'h1',t);add(app,'p',lead,'lead')};
const box=(t:string)=>add(app,'p',t,'notice');
const table=(headers:string[],rows:any[][],parent:Element=app)=>{const wrap=add(parent,'div',undefined,'data-table');const t=add(wrap,'table');const head=add(t,'thead');const h=add(head,'tr');headers.forEach(x=>add(h,'th',x));const body=add(t,'tbody');rows.forEach(row=>{const tr=add(body,'tr');row.forEach(cell=>{const td=add(tr,'td');if(cell instanceof Node)td.append(cell);else td.textContent=cell===null||cell===undefined?'未知':String(cell)})});return t};
const badge=(r:any)=>[labels[r.evidence_grade]||r.evidence_grade,labels[r.validation_status]||r.validation_status].filter(Boolean).join(' · ');
const metric=(parent:Element,label:string,value:any,note:string)=>{const c=add(parent,'article',undefined,'card');add(c,'div',label,'muted');add(c,'div',value??'未知','metric');add(c,'p',note,'muted')};
const paperURL=(id:string)=>base+'paper/?id='+encodeURIComponent(id);
const sourceURL=(v:any)=>v.source_url+(v.source_page?'#page='+v.source_page:'');
function exportRows(rows:any[],name:string){const keys=rows.length?Object.keys(rows[0]):[];const quote=(v:any)=>'"'+(v===null||v===undefined?'':typeof v==='object'?JSON.stringify(v):String(v)).replaceAll('"','""')+'"';const csv='\ufeff'+[keys.join(','),...rows.map(r=>keys.map(k=>quote(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=e('a') as HTMLAnchorElement;a.href=url;a.download=name+'.csv';a.click();URL.revokeObjectURL(url)}
function control(parent:Element,label:string,options:[string,string][],initial='',multi=false){const l=add(parent,'label',label);const s=add(l,'select') as HTMLSelectElement;s.setAttribute('aria-label',label);s.multiple=multi;if(multi)s.size=3;options.forEach(([value,text])=>{const o=add(s,'option',text) as HTMLOptionElement;o.value=value;o.selected=value===initial});return s}
const input=(parent:Element,label:string,initial='')=>{const l=add(parent,'label',label);const n=add(l,'input') as HTMLInputElement;n.setAttribute('aria-label',label);n.value=initial;return n};

async function dashboard(){const [r,vars]=await Promise.all([get('coverage_report'),get('variables')]);title('策略研究，從分類走向來源證據','自動處理 SMJ 書目、摘要分類與合法正文衡量。Taxonomy v2 保留 SMS 參照與獨立 Theory 維度，非 SMJ 官方分類。');const grid=add(app,'div',undefined,'grid');metric(grid,'索引書目',r.papers,'DOI 去重；歷史涵蓋率未完成出版社對帳');metric(grid,'已自動分類論文',r.classified_papers,`分母 ${r.classification_denominator}；來源一致性不等於專家審閱`);metric(grid,'可解析正文',r.accessible_fulltexts,`已嘗試 ${r.fulltexts_attempted} 篇；不公開全文`);metric(grid,'衡量文字對齊',r.measurement_text_aligned,`${r.verified_papers} 篇 / ${r.papers}；有原文公式 ${r.formula_backed_variables} 筆`);metric(grid,'研究假設與結果',r.study_claim_records??0,`假設 ${r.hypothesis_records??0} · 結果 ${r.finding_records??0} · Robustness ${r.robustness_records??0}`);box('未取得原始證據的公式、模型角色、樣本期間、估計方法與係數均保留未知。自動分類可直接使用，無需你逐篇核准。');add(app,'p',`書目年份 ${r.years[0]}–${r.years.at(-1)} · 摘要來源 ${r.abstracts_available} 篇 · 最近成功書目同步（UTC）${r.last_successful_sync||'未知'}`,'muted');const routes=add(app,'div',undefined,'grid');for(const [path,h,t] of [['landscape','研究地圖','四層導覽與多重標記'],['papers','論文搜尋','模糊搜尋、來源與可分享篩選'],['variables','變數字典','逐篇衡量與未知欄位'],['analytics','研究趨勢與分析','明列分母的趨勢及共現'],['run','啟動論文抓取與分析','從 GitHub 授權啟動批次自動擷取']]){const a=link(routes,h,base+path+'/');a.className='card';add(a,'p',t,'muted')}add(app,'h2','具衡量文字來源的代表論文');for(const v of vars.slice(0,5)){const c=add(app,'article',undefined,'record');link(c,v.paper_title||v.paper_id,paperURL(v.paper_id));add(c,'p',v.variable_label_original+' · '+badge(v),'status-line');link(c,'原始來源與頁碼',sourceURL(v))}}

async function explorer(){const [rows,tax]=await Promise.all([get('papers'),get('taxonomy')]);title('論文搜尋','搜尋標題、作者、DOI、主題、理論、構念及已擷取變數。自動分類預設可用；未知資訊不會以推測填補。');const nodes=new Map(tax.nodes.map((n:any)=>[n.id,n]));rows.forEach((p:any)=>p.search_terms=[...Object.values(p.taxonomy_tags.active).flat().map((id:any)=>(nodes.get(id) as any)?.label_en||id),...(p.variable_labels||[])].join(' '));const fuse=new Fuse(rows,{keys:['title','authors','doi','search_terms'],threshold:.32,ignoreLocation:true});const controls=add(app,'div',undefined,'controls');const q=input(controls,'搜尋',params.get('q')||'');const year=control(controls,'年份',[['','全部年份'],...[...new Set(rows.map((p:any)=>p.publication_year))].sort().map(y=>[String(y),String(y)] as [string,string])],params.get('year')||'');const facet:Record<string,HTMLSelectElement>={};for(const [id,level,label] of [['domain','domain','Domain'],['topic','research_topic','Research Topic'],['construct','construct','Construct'],['theory','theory','Theory']]){facet[id]=control(controls,label,[['','全部'],...tax.nodes.filter((n:any)=>n.level===level).map((n:any)=>[n.id,n.label_zh] as [string,string])],'',true);const saved=params.getAll(id);for(const o of facet[id].options)o.selected=saved.length?saved.includes(o.value):!o.value}const mode=control(controls,'分類品質',[['active','自動可用（含暫定）'],['automatic','僅來源一致性通過'],['approved','僅歷史人工確認'],['candidate','弱監督候選（不可視為作者使用理論）']],params.get('mode')==='candidate'?'candidate':params.get('mode')==='approved'?'approved':params.get('mode')==='automatic'?'automatic':'active');const grade=control(controls,'論文至少具一筆分類證據',[['','不限'],['E0_metadata','E0 書目'],['E1_abstract','E1 摘要']],params.get('grade')||'');const full=control(controls,'正文',[['','不限'],['yes','已解析正文']],params.get('fulltext')||'');const sort=control(controls,'排序',[['relevance','相關度'],['newest','年份由新至舊'],['citations','OpenAlex 引用數'],['title','標題']],params.get('sort')||'relevance');const status=add(app,'p','','status-line');status.setAttribute('role','status');const exp=add(app,'button','匯出目前篩選 CSV');const results=add(app,'div');const pager=add(app,'div',undefined,'toolbar');const prev=add(pager,'button','上一頁') as HTMLButtonElement;const info=add(pager,'span');const next=add(pager,'button','下一頁') as HTMLButtonElement;let page=Math.max(0,Number(params.get('page')||'1')-1),filtered:any[]=[];
function render(reset=false){if(reset)page=0;const matched=q.value.trim()?fuse.search(q.value.trim()).map(r=>r.item):rows.slice();filtered=matched.filter((p:any)=>(!year.value||String(p.publication_year)===year.value)&&(!grade.value||p.evidence_grades.includes(grade.value))&&(!full.value||p.fulltext_accessible)&&Object.entries(facet).every(([id,s])=>{const wanted=Array.from(s.selectedOptions).map(o=>o.value).filter(Boolean);const level={domain:'domain',topic:'research_topic',construct:'construct',theory:'theory'}[id]!;return !wanted.length||wanted.some(t=>p.taxonomy_tags[mode.value]?.[level]?.includes(t))}));if(sort.value==='newest'||(!q.value&&sort.value==='relevance'))filtered.sort((a,b)=>b.publication_year-a.publication_year||a.paper_id.localeCompare(b.paper_id));if(sort.value==='citations')filtered.sort((a,b)=>(b.citation_count??-1)-(a.citation_count??-1)||a.paper_id.localeCompare(b.paper_id));if(sort.value==='title')filtered.sort((a,b)=>a.title.localeCompare(b.title));page=Math.min(page,Math.max(0,Math.ceil(filtered.length/25)-1));status.textContent=`${filtered.length} / ${rows.length} 篇 · 多選同維度 OR、跨維度 AND · 自動來源檢查非專家審閱`;results.replaceChildren();for(const p of filtered.slice(page*25,(page+1)*25)){const c=add(results,'article',undefined,'paper');add(c,'p',`${p.publication_year} · ${p.evidence_grades.map((g:string)=>labels[g]).join(' / ')} · ${p.fulltext_accessible?'正文可解析':'正文未知'}`,'status-line');const h=add(c,'h2');link(h,p.title,paperURL(p.paper_id));add(c,'p',p.authors.join(', '),'muted');link(c,p.doi,'https://doi.org/'+p.doi)}if(!filtered.length)add(results,'p','沒有符合條件的紀錄；未分類不表示不屬於該主題。','empty');info.textContent=`${page+1} / ${Math.max(1,Math.ceil(filtered.length/25))}`;prev.disabled=page===0;next.disabled=(page+1)*25>=filtered.length;const url=new URL(location.href);url.search='';for(const [k,v] of [['q',q.value],['year',year.value],['mode',mode.value],['grade',grade.value],['fulltext',full.value],['sort',sort.value],['page',String(page+1)]])if(v)url.searchParams.set(k,v);for(const [id,s] of Object.entries(facet))for(const o of s.selectedOptions)if(o.value)url.searchParams.append(id,o.value);history.replaceState(null,'',url)}for(const select of Object.values(facet)){
  let previous=Array.from(select.selectedOptions).map(o=>o.value);
  select.addEventListener('change',()=>{
    const current=Array.from(select.selectedOptions).map(o=>o.value);
    if(current.includes('')&&!previous.includes('')) {
      for(const opt of select.options)opt.selected=!opt.value;
    } else if(current.some(Boolean)) {
      select.options[0].selected=false;
    } else {
      select.options[0].selected=true;
    }
    previous=Array.from(select.selectedOptions).map(o=>o.value);
    render(true);
  });
}
const clear=add(controls,'button','全部／清除分類條件') as HTMLButtonElement;
clear.type='button';
clear.onclick=()=>{for(const select of Object.values(facet)){for(const opt of select.options)opt.selected=!opt.value;}render(true)};
controls.addEventListener('input',()=>render(true));prev.onclick=()=>{page--;render()};next.onclick=()=>{page++;render()};exp.onclick=()=>exportRows(filtered.map(({search_terms,...p})=>p),'smj-papers');render()}

/** On-demand, public OpenAlex abstract display: no full abstract is
 * stored in the repository or static published JSON. Availability differs
 * from evidence of academic topic and does not imply a reusable license.
 */
async function showAbstract(parent:Element,extra:any,doi:string){
  const area=add(parent,'div',undefined,'record');
  const h=add(area,'h3','Abstract / 論文摘要');
  const status=add(area,'p','從 OpenAlex 讀取可用的摘要…','muted');
  const id=String(extra?.openalex_id||'').match(/^https:\/\/openalex\.org\/(W\d+)$/);
  const publisher=add(area,'p','來源：OpenAlex 摘要索引；使用時請保留原出版文獻引用。','tiny');
  const a=add(area,'a','查看出版社原始摘要') as HTMLAnchorElement;
  a.href='https://doi.org/'+encodeURI(doi);
  a.target='_blank';a.rel='noopener noreferrer';
  if(!id || !extra?.abstract_available){
    status.textContent='目前沒有可供重建的 OpenAlex 摘要；可由 DOI 開啟出版社摘要。';
    return;
  }
  try{
    const url='https://api.openalex.org/works/'+id[1]+'?select=id,abstract_inverted_index';
    const response=await fetch(url,{headers:{Accept:'application/json'}});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const json=await response.json();
    if(json.id!==extra.openalex_id)throw new Error('identity_mismatch');
    const index=json.abstract_inverted_index;
    if(!index||typeof index!=='object')throw new Error('abstract_missing');
    const positions:Array<[number,string]>=[];
    for(const [word,indices] of Object.entries(index)){
      if(!Array.isArray(indices)||indices.length>2500)continue;
      for(const n of indices){
        if(Number.isInteger(n)&&n>=0&&n<5000)positions.push([n,word]);
      }
    }
    positions.sort((a,b)=>a[0]-b[0]);
    if(!positions.length||positions.length>5000)throw new Error('abstract_invalid');
    status.textContent=positions.map(p=>p[1]).join(' ');
    publisher.textContent='直接由 OpenAlex 公開 API 顯示（非 Atlas 儲存／重刊）；原文權利仍屬其權利人。';
  }catch{
    status.textContent='目前無法從 OpenAlex 載入摘要；可由 DOI 開啟出版社摘要。';
  }
}

async function profile(){const id=params.get('id');if(!id)throw Error('缺少 paper_id');const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(id));const hash=Array.from(new Uint8Array(bytes)).map(b=>b.toString(16).padStart(2,'0')).join('').slice(0,16);const [p,tax]=await Promise.all([get('papers/'+hash),get('taxonomy')]);title(p.title,p.authors.join(', '));add(app,'p',`${p.publication_year} · SMJ ${p.volume??'未知卷'} (${p.issue??'未知期'}) · ${p.pages??'未知頁碼'}`);link(app,'DOI / 出版社',p.doi_url);const receipt=p.content_access;const enriched=p.enrichment;add(app,'p',`正文：${receipt.accessible?'已解析（'+receipt.version+'）':'未知／不可取得'} · 摘要：${enriched?.abstract_available?'已取得供分類使用；不重刊全文':'未知'}`,'status-line');if(receipt.source_url)link(app,'合法正文來源',receipt.source_url);
const onDemand=add(app,'section',undefined,'record');
add(onDemand,'h3','指定這篇論文：按需分析（限 Atlas 專案擁有人）');
add(onDemand,'p','不必等待全庫爬蟲：送出 GitHub Issue 後會只針對這篇 DOI 嘗試合法 OA 正文，回覆假設／命題、實證結果與穩健性，及 sample_period、data_source、empirical_method。Review 文章會標明暫定不適用，不會把取不到正文解讀成研究沒有假設。','muted');
const query='Atlas analyze: '+p.doi;
const body='DOI: '+p.doi+'\\nTitle: '+p.title;
const issueURL='https://github.com/oliver0923-hub/smj-research-atlas/issues/new?title='+encodeURIComponent(query)+'&body='+encodeURIComponent(body);
link(onDemand,'啟動這篇論文的單篇深入擷取（開啟預填 GitHub Issue，送出後執行）',issueURL);
box('本頁自動驗證的是來源、文字對齊與資料一致性，不是人工專家審閱；沒有從標題推定公式、係數或因果效果。');add(app,'h2','研究分類總覽');
void showAbstract(app,enriched,p.doi);
const publishedOa=(enriched?.oa_locations||[]).find((x:any)=>String(x.pdf_url||'').startsWith('https://sms.onlinelibrary.wiley.com/doi/pdfdirect/')&&x.is_oa&&x.is_published);
if(publishedOa){const publisher=add(app,'p');link(publisher,'Wiley 已標記 OA 的原版 PDF（實際下載權限以出版社為準）',publishedOa.pdf_url)}
const classMap=new Map(tax.nodes.map((n:any)=>[n.id,n]));
const categoryLabels:Record<string,string>={domain:'Domain',research_topic:'Research Topic',construct:'Construct',theory:'Theory'};
const paramKeys:Record<string,string>={domain:'domain',research_topic:'topic',construct:'construct',theory:'theory'};
const qualityLabels:Record<string,string>={fulltext_author_declared:'全文作者明示（E2）',abstract_supported:'摘要詞彙支持',title_supported:'標題詞彙支持',provisional:'暫定相似分類',unresolved_other:'其他／未判定',human_approved:'歷史人工確認'};
for(const level of ['domain','research_topic','construct','theory']){
    const c=add(app,'article',undefined,'record');
    add(c,'h3',categoryLabels[level]);
    const quality=p.taxonomy_quality?.[level];
    add(c,'p',qualityLabels[quality?.state]||'尚未編碼','status-line');
    for(const id of p.taxonomy_tags.active[level]||[]){
        const n:any=classMap.get(id);if(!n)continue;
        const line=add(c,'p');
        link(line,n.label_zh+' / '+n.label_en,base+'papers/?'+paramKeys[level]+'='+encodeURIComponent(id));
    }
    const candidates=p.taxonomy_tags?.candidate?.[level]||[];
    if(candidates.length){
       add(c,'h4','可能相關的構念／理論視角（弱監督候選，尚未驗證）');
       for(const id of candidates){
           const n:any=classMap.get(id);if(!n)continue;
           const line=add(c,'p');
           link(line,n.label_zh+' / '+n.label_en,base+'papers/?mode=candidate&'+paramKeys[level]+'='+encodeURIComponent(id));
           const match=p.classifications?.find((a:any)=>a.term_id===id&&a.is_semantic_candidate);
           if(match)add(line,'span',' · 線索：'+(match.weak_trigger||'語境詞組')+' · 未確認使用','tiny');
       }
    }
    if(quality?.is_unresolved)add(c,'p','尚無足夠證據確認此維度；上方弱監督候選不等於作者引用理論或實測構念。','tiny');
    else add(c,'p','自動來源證據分級：'+(quality?.best_evidence_grade||'未提供')+' · 相似度分數不是正確機率','tiny');
}
if(p.research_v4)renderV4(p.research_v4);if(!p.research_v4){add(app,'h2','假設、實證結果與穩健性');
const studies:Array<any>=p.study_claims||[];
add(app,'p','僅顯示能在合法取得的正文中定位之敘述。顯著與支持假設不同；未辨識到不等於不顯著或沒有檢驗。','status-line');
if(!studies.length)add(app,'p','目前尚無可對齊的假設／結果／穩健性證據；不代表論文未提出假設或未執行檢驗。','empty');
const claimLabels:Record<string,string>={hypothesis:'研究假設',proposition:'理論命題',finding:'實證結果',robustness:'穩健性檢驗',sensitivity:'敏感性分析'};
const supportLabels:Record<string,string>={supported:'支持',not_supported:'不支持',partially_supported:'部分支持',mixed:'混合結果',unknown:'未確認'};
const significanceLabels:Record<string,string>={significant:'顯著',not_significant:'不顯著',mixed:'混合',unknown:'未確認'};
const checkLabels:Record<string,string>={holds:'維持',does_not_hold:'不維持',mixed:'混合結果',unknown:'未確認'};
for(const kind of ['hypothesis','proposition','finding','robustness','sensitivity']){
  const group=studies.filter((c:any)=>c.claim_type===kind);
  if(!group.length)continue;
  add(app,'h3',claimLabels[kind]);
  for(const c of group){
    const card=add(app,'article',undefined,'record');
    add(card,'h4',c.label||c.hypothesis_label||claimLabels[kind]);
    add(card,'p',c.statement_excerpt+'（原文短摘錄，可能非完整句子）');
    if(kind==='finding'){
      add(card,'p','假設支持：'+supportLabels[c.support_status||'unknown']+' · 統計顯著：'+significanceLabels[c.significance||'unknown'],'status-line');
      if(!c.related_hypothesis_id)add(card,'p','對應假設原文尚未自動定位','tiny');
    }
    if(kind==='robustness'||kind==='sensitivity')add(card,'p','檢驗結果：'+checkLabels[c.robustness_result||'unknown'],'status-line');
    link(card,c.evidence_locator,c.source_url+(c.source_page?'#page='+c.source_page:''));
    add(card,'p','來源文字定位自動驗證 · 非人工審閱 · '+c.algorithm_version,'tiny');
  }
}
add(app,'h2','逐篇衡量');if(!p.variables.length)add(app,'p','尚無來源文字可支持的變數紀錄。變數、公式、樣本、方法與結果保留未知。','empty');for(const v of p.variables){const c=add(app,'article',undefined,'record');c.id=v.variable_id;add(c,'h3',v.variable_label_original);add(c,'p',badge(v),'status-line');add(c,'p',v.operational_definition);const dl=add(c,'dl');for(const [name,value] of [['角色',labels[v.role]||v.role],['代理衡量',v.proxy_name],['公式（僅原文寫出時）',v.formula],['單位',v.unit],['落後期',v.lag],['樣本期間',v.sample_period],['資料來源',v.data_source],['估計方法',v.empirical_method],['報告關係／係數',v.reported_association]]){add(dl,'dt',name);add(dl,'dd',value??'未知：該擷取段落未提供或尚未驗證')}add(c,'blockquote',v.evidence_excerpt,'evidence');link(c,v.evidence_locator,sourceURL(v));add(c,'p','版本 '+v.algorithm_version+' · 檢查時間 '+v.retrieved_at+' · 原始檔 hash '+v.source_hash,'tiny')}}add(app,'h2','分類與證據');const nodes=new Map(tax.nodes.map((n:any)=>[n.id,n]));for(const a of p.classifications.filter((a:any)=>a.review_status!=='rejected')){const c=add(app,'article',undefined,'record');const n:any=nodes.get(a.term_id);add(c,'h3',`${n.level} · ${n.label_zh}`);add(c,'p',badge(a)+' · '+a.inference_origin,'status-line');link(c,a.evidence_locator,a.source_url);add(c,'p',`方法 ${a.method} · heuristic_score ${a.heuristic_score??'不適用'}（非機率） · taxonomy ${a.taxonomy_version}`,'tiny')}add(app,'h2','尚未知的研究資訊');table(['欄位','值'],Object.entries(p.unknown_details).map(([k,v])=>[k,v]));if(location.hash)document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView()}

async function dictionary(){const vars=await get('variables');title('逐篇變數字典','每筆變數連到其論文與原始測量段落。近似名稱不自動視為同一構念，異質衡量不可直接合併。');box(`目前 ${vars.length} 筆衡量文字紀錄；不是每篇論文的完整變數清單。公式、模型角色與期間等未經證據支持者仍為未知。`);const controls=add(app,'div',undefined,'controls');const q=input(controls,'搜尋構念／變數／proxy',params.get('q')||'');const role=control(controls,'角色',[['','全部'],...['independent','dependent','mediator','moderator','control','instrument','unknown'].map(x=>[x,labels[x]] as [string,string])]);const output=add(app,'div');const count=add(app,'p','','status-line');count.setAttribute('role','status');const exp=add(app,'button','匯出目前變數 CSV');let filtered=vars;function render(){filtered=vars.filter((v:any)=>(!q.value||[v.construct_en,v.construct_zh,v.variable_label_original,v.proxy_name].join(' ').toLowerCase().includes(q.value.toLowerCase()))&&(!role.value||v.role===role.value));output.replaceChildren();table(['構念／變數','逐篇定義與 proxy','公式／單位／角色','來源與證據'],filtered.map((v:any)=>{const name=e('div');link(name,v.variable_label_original,paperURL(v.paper_id)+'#'+encodeURIComponent(v.variable_id));add(name,'p',v.paper_title||v.paper_id,'tiny');const def=e('div',v.operational_definition);add(def,'p',v.proxy_name??'proxy 未知','muted');const evidence=e('div',badge(v));link(evidence,v.evidence_locator,sourceURL(v));return [name,def,`${v.formula??'公式未知'} / ${v.unit??'單位未知'} / ${labels[v.role]||v.role}`,evidence]}),output);count.textContent=`${filtered.length} / ${vars.length} 筆；E3 表示有衡量文字，不表示已經專家確認。`;}controls.addEventListener('input',render);exp.onclick=()=>exportRows(filtered,'smj-variables');render()}

async function quality(){const [r,history]=await Promise.all([get('coverage_report'),get('pipeline_history')]);title('自動品質與涵蓋率','來源、缺失值與執行紀錄均可查核。未知不等於零，來源檢查不等於專家同行審閱。');box('出版社目錄目前無法完整取得；整個 SMJ 母體分母、漏收比例與歷史完整性仍未知。不得將現有索引數量稱為期刊全部論文。');table(['指標','實際值'],[['書目 / 去重 DOI',`${r.papers} / ${r.unique_doi}`],['重複 DOI',r.duplicate_doi],['已補充 OpenAlex',`${r.enriched_papers} / ${r.papers}`],['摘要來源可用',`${r.abstracts_available} / ${r.papers}`],['可解析正文 / 已嘗試',`${r.accessible_fulltexts} / ${r.fulltexts_attempted}`],['有衡量文字之論文',`${r.verified_papers} / ${r.papers}`],['原文公式紀錄',r.formula_backed_variables],['假設紀錄',r.hypothesis_records??0],['實證結果敘述',r.finding_records??0],['穩健性檢驗',r.robustness_records??0],['敏感性分析',r.sensitivity_records??0],['出版社 HTTP',r.publisher_reconciliation.http_status],['出版社完整分母',r.publisher_reconciliation.expected_articles],['估計漏收比例',r.missing_publisher_coverage_estimate],['最近成功書目同步（UTC）',r.last_successful_sync],['Schema / taxonomy',r.schema_version+' / '+r.taxonomy_version]]);add(app,'h2','分類證據分布');table(['等級','分類紀錄數'],Object.entries(r.evidence_tiers));add(app,'h2','原始欄位缺失（分母為索引書目）');table(['欄位','缺失筆數'],Object.entries(r.missing_fields));add(app,'h2','已記錄執行');table(['模式','狀態','開始（UTC）','秒數'],history.map((h:any)=>[h.mode,h.status,h.started_at,h.runtime_seconds]));link(app,'GitHub 即時工作狀態與錯誤日誌','https://github.com/oliver0923-hub/smj-research-atlas/actions');add(app,'p','自動工作失敗時保留最近一次通過檢查的網站。同步、擷取與分類不需要擁有者逐篇審核。','notice');link(app,'下載來源與逐年卷期涵蓋紀錄',base+'data/coverage_issues.json')}

async function theories(){const [tax,a]=await Promise.all([get('taxonomy'),get('analytics')]);title('理論導覽','GitHub 週更由書目與摘要規則辨識理論提及，每次成功發布自動重算。Theory 與 Domain／Topic 獨立，未明示的理論不推定為已使用。');box('以下是字詞來源一致的自動標記，不能據此確認理論在研究中扮演的角色、機制或因果解釋。尚未辨識者保持未知；不需要擁有者逐篇核准。');add(app,'p',`分析生成時間（UTC）：${a.generated_at}`,'muted');for(const t of tax.nodes.filter((n:any)=>n.level==='theory')){const c=add(app,'article',undefined,'record');add(c,'h2',t.label_zh+' / '+t.label_en);const facts=a.paper_facts.filter((p:any)=>!['editorial_or_notice','retracted'].includes(p.kind)&&p.tags.some((x:any)=>x.term_id===t.id));const grades:Record<string,number>={};facts.forEach((p:any)=>{const tag=p.tags.find((x:any)=>x.term_id===t.id);grades[tag.grade]=(grades[tag.grade]||0)+1});add(c,'p',`${facts.length} / ${a.denominator} 篇 · ${Object.entries(grades).map(([k,v])=>(labels[k]||k)+' '+v+' 篇').join('；')}`,'status-line');link(c,'探索此理論與逐篇來源',base+'papers/?theory='+t.id);for(const p of facts.slice(0,4)){const h=add(c,'p');link(h,p.title,paperURL(p.paper_id))}}}

async function gaps(){const [r,tax]=await Promise.all([get('gap_candidates'),get('taxonomy')]);title('自動研究機會候選','GitHub 程序依目前文獻的主題標記、共現篇數與來源覆蓋，自動重算可追蹤的研究組合。這是探索起點，並非已確認的學術研究缺口。');box('不將「沒有辨識到」解讀為「沒有研究」；新穎性、機制與研究可行性尚未驗證時保留未知。候選建議無須人工核准即可瀏覽。');add(app,'p',`生成時間（UTC）${r.generated_at} · 索引分析分母 ${r.denominator} 篇 · ${r.candidates.length} 組候選`,'status-line');const search=input(app,'搜尋候選主題','');const out=add(app,'div');function render(){out.replaceChildren();const rows=r.candidates.filter((x:any)=>(x.label_a+' '+x.label_b+' '+x.topic_a+' '+x.topic_b).toLowerCase().includes(search.value.toLowerCase()));if(!rows.length)add(out,'p','目前規則下沒有符合的候選；不表示不存在研究機會。','empty');for(const x of rows){const c=add(out,'article',undefined,'record');add(c,'h2',x.label_a+' × '+x.label_b);add(c,'p',`主題 A ${x.papers_a} 篇；主題 B ${x.papers_b} 篇；共同 ${x.joint_papers} / ${x.denominator} 篇`,'status-line');add(c,'p',`規則：各主題至少 ${x.rule.minimum_each_topic} 篇，合併至多 ${x.rule.maximum_joint} 篇。暫定候選 · ${x.algorithm_version} · taxonomy ${x.taxonomy_version}`,'muted');link(c,'探索主題 A',base+'papers/?topic='+x.topic_a);add(c,'span',' · ');link(c,'探索主題 B',base+'papers/?topic='+x.topic_b);add(c,'p','已驗證研究缺口：未知；新穎性：未知；因果機制：未知。');add(c,'h3','支撐書目與可追溯分類');for(const id of [...new Set([...x.joint_paper_ids,...x.support_paper_ids_a.slice(0,2),...x.support_paper_ids_b.slice(0,2)])] as string[]){const p=add(c,'p');link(p,id,paperURL(id))}add(c,'p','共現的理論標記：'+(x.associated_theories.map((t:any)=>t.label+' '+t.papers+' 篇').join('；')||'尚未辨識，保留未知'),'muted')}}search.oninput=render;render();r.limitations.forEach((x:string)=>add(app,'p',x,'muted'));link(app,'下載候選規則與來源紀錄 JSON',base+'data/gap_candidates.json')}

async function automaticQuality(){
const [r,discovered]=await Promise.all([get('coverage_report'),get('emerging_topics')]);
title('自動分類品質與證據','每篇論文的 Domain、Research Topic、Construct、Theory 都有可查詢狀態；其他／未判定是拒絕猜測的標記，不是正式學術類別。');
const dims:[string,string,string][]=[['domain','Domain','domain'],['research_topic','Research Topic','topic'],['construct','Construct','construct'],['theory','Theory','theory']];
const stats=r.classification_by_dimension||{};
add(app,'h2','四個維度的實際辨識率');
table(['分類維度','全文作者明示 E2','摘要支持 E1','標題支持 E0','暫定','其他／未判定','弱監督候選','候選新增涵蓋','具來源分類／全部'],dims.map(([level,label,filter])=>{
const a=stats[level]||{};const other=a.unresolved_other??r.papers;
const otherLink=e('div');const href=base+'papers/?'+filter+'=OTHER-'+({domain:'DOM',research_topic:'TOP',construct:'CON',theory:'TH'} as Record<string,string>)[level];
link(otherLink,String(other)+' 篇（查看）',href);
return [label,a.fulltext_author_declared??0,a.abstract_supported??0,a.title_supported??0,a.provisional??0,otherLink,a.weak_candidate_papers??0,a.additional_candidate_only_papers??0,`${a.substantive_papers??0} / ${a.denominator??r.papers}`];
}));
box('「全文作者明示 E2」指可合法取得的正文中，作者在理論相關章節以明確語句陳述採用某個理論視角；這是自動來源文字對齊，並非獨立的學者語義認證。僅提及理論會顯示在弱候選，不納入實質分類。「其他」不等於沒有理論。');
add(app,'h2','其他／未判定：缺失來源診斷');
table(['維度','尚無摘要','已有摘要、等待最新版詞典重索引','已用最新版摘要詞典掃描仍未命中'],dims.map(([level,label])=>{
 const a=stats[level]||{};
 return [label,a.unresolved_without_abstract??'未提供',a.unresolved_pending_feature_backfill??'未提供',a.unresolved_after_current_abstract_scan??'未提供'];
}));
add(app,'p','這些是資料處理進度與詞彙吻合狀態，不等於論文未引用理論或未定義研究構念。摘要與正文的涵蓋範圍不同。','muted');
add(app,'h2','分類品質定義');
table(['狀態','解讀'],[['fulltext_author_declared','作者在合法正文理論相關章節明確自述採用該理論（E2，仍非專家驗證）'],['abstract_supported','OpenAlex 摘要的對應關鍵詞命中（E1）'],['title_supported','Crossref 標題的明確詞組命中，或由 Atlas 層級往上對應（E0）'],['provisional','標題詞彙相似推測；需要保守解讀'],['semantic_candidate','弱監督多詞組候選；不證明實際採用理論或衡量構念'],['unresolved_other','沒有充分辨識證據；使用其他／未判定標籤'],['human_approved','僅歷史上確有明確紀錄的人工作業，不代表自動分類已審閱']]);
add(app,'h2','自動來源一致性檢查');
table(['來源或規則狀態','紀錄數'],Object.entries(r.validation_statuses||{}));
add(app,'h2','新興詞彙候選');
add(app,'p','詞彙成長候選，不自動提升為官方領域或可確認理論；來源分母與詞彙比率供查核。','muted');
table(['詞彙','近期文件 / 分母','前期文件 / 分母','平滑相對比例','狀態'],discovered.map((d:any)=>[d.label_en,`${d.recent_documents} / ${d.recent_denominator}`,`${d.baseline_documents} / ${d.baseline_denominator}`,d.smoothed_prevalence_ratio,'discovered_topic / provisional']));
link(app,'檢視完整來源與計算欄位',base+'data/emerging_topics.json')
}

const svg=(tag:string,attrs:Record<string,any>,parent:Element,text?:string)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text)n.textContent=text;parent.append(n);return n};
async function analytics(){const [a,tax]=await Promise.all([get('analytics'),get('taxonomy')]);title('研究趨勢與描述性分析','計算範圍是目前索引書目，排除標題明確標示的社論／更正；其他研究文章類型仍有未確認者。多重標記比例不可相加為 100%。');const controls=add(app,'div',undefined,'controls');const g=control(controls,'分類證據',[['','所有可用分類'],['E0_metadata','E0 書目'],['E1_abstract','E1 摘要']]);const topic=control(controls,'趨勢主題',[['','索引篇數'],...tax.nodes.filter((n:any)=>n.level==='research_topic').map((n:any)=>[n.id,n.label_zh] as [string,string])]);const full=control(controls,'分析正文範圍',[['','全部索引'],['yes','僅可解析正文']]);const output=add(app,'div');function render(){output.replaceChildren();const facts=a.paper_facts.filter((p:any)=>!['editorial_or_notice','retracted'].includes(p.kind)&&(!full.value||p.fulltext)).map((p:any)=>({...p,selected:p.tags.filter((t:any)=>!g.value||t.grade===g.value)})).filter((p:any)=>!g.value||p.selected.length);add(output,'p',`目前分母：${facts.length} 篇；${g.value?'限至少有一筆所選證據等級之分類':'包含未分類書目'}。近期未完整年度不可直接與完整年度比較。`,'notice');const years=[...new Set(a.paper_facts.map((p:any)=>p.year))].sort() as number[];const values=years.map(y=>{const rows=facts.filter((p:any)=>p.year===y);const n=topic.value?rows.filter((p:any)=>p.selected.some((t:any)=>t.term_id===topic.value)).length:rows.length;return {year:y,n,N:rows.length,value:topic.value?(rows.length?n/rows.length:0):n}});add(output,'h2',topic.value?'主題占當年篩選書目的比例':'目前索引的年度篇數');const chart=svg('svg',{},output) as any;chart.setAttribute('viewBox','0 0 900 280');chart.classList.add('chart');chart.setAttribute('role','img');chart.setAttribute('aria-label','依當前證據與正文範圍篩選的年度趨勢');const max=Math.max(.01,...values.map(v=>v.value));svg('line',{x1:45,x2:880,y1:235,y2:235,stroke:'#829587'},chart);values.forEach((v,i)=>{const h=v.value/max*190;const bar=svg('rect',{x:48+i*830/values.length,y:235-h,width:Math.max(2,830/values.length-3),height:h,fill:v.year===Math.max(...years)?'#b48b47':'#38745d'},chart);svg('title',{},bar,`${v.year}: ${topic.value?(v.value*100).toFixed(1)+'%':v.n+' 篇'} (${v.n}/${v.N})`)});svg('text',{x:45,y:25,'font-size':13},chart,topic.value?`上界 ${(max*100).toFixed(1)}%`:`上界 ${max} 篇`);svg('text',{x:45,y:265,'font-size':13},chart,String(years[0]));svg('text',{x:825,y:265,'font-size':13},chart,String(years.at(-1)));const details=add(output,'details');add(details,'summary','檢視年度精確數值與分母');table(['年','篇數','當年分母','比例'],values.map(v=>[v.year,v.n,v.N,v.N?(v.n/v.N*100).toFixed(2)+'%':'未知']),details);
const counts=new Map<string,number>(),pairs=new Map<string,number>();for(const p of facts){const ts=[...new Set(p.selected.filter((t:any)=>t.term_id.startsWith('TOP-')).map((t:any)=>t.term_id))].sort() as string[];for(const t of ts)counts.set(t,(counts.get(t)||0)+1);for(let i=0;i<ts.length;i++)for(let j=i+1;j<ts.length;j++){const key=ts[i]+'|'+ts[j];pairs.set(key,(pairs.get(key)||0)+1)}}add(output,'h2','主題共現網絡');add(output,'p','同篇論文的自動標記共現，不代表理論關係、因果連結或新穎性。點選節點可前往文獻搜尋。','muted');const top=[...counts].sort((a,b)=>b[1]-a[1]).slice(0,12);const network=svg('svg',{},output) as any;network.setAttribute('viewBox','0 0 640 400');network.classList.add('chart');network.setAttribute('role','img');network.setAttribute('aria-label','前十二個主題的論文共現網絡');const pos=new Map(top.map(([id],i)=>[id,{x:320+155*Math.cos(i/top.length*Math.PI*2),y:200+155*Math.sin(i/top.length*Math.PI*2)}]));for(const [key,n] of pairs){const [a,b]=key.split('|'),x=pos.get(a),y=pos.get(b);if(x&&y)svg('line',{x1:x.x,y1:x.y,x2:y.x,y2:y.y,stroke:'#b5c8b8','stroke-width':Math.min(6,1+Math.log(n))},network)}top.forEach(([id,n],i)=>{const p=pos.get(id)!;const a=svg('a',{href:base+'papers/?topic='+id},network);const c=svg('circle',{cx:p.x,cy:p.y,r:18,fill:'#245c48'},a);svg('title',{},c,tax.nodes.find((t:any)=>t.id===id).label_zh+': '+n+'篇');svg('text',{x:p.x,y:p.y+4,'text-anchor':'middle',style:'fill:white','font-size':12},a,String(i+1))});table(['節點','主題','篇數 / 目前分母'],top.map(([id,n],i)=>[i+1,tax.nodes.find((t:any)=>t.id===id).label_zh,`${n} / ${facts.length}`]),output);
add(output,'h2','Theory × Topic（同篇標記）');const matrix=new Map<string,number>();for(const p of facts){const theories=[...new Set(p.selected.filter((t:any)=>t.term_id.startsWith('TH-')).map((t:any)=>t.term_id))] as string[];const topics=[...new Set(p.selected.filter((t:any)=>t.term_id.startsWith('TOP-')).map((t:any)=>t.term_id))] as string[];for(const th of theories)for(const to of topics){const k=th+'|'+to;matrix.set(k,(matrix.get(k)||0)+1)}}table(['理論','主題','共現篇數'],[...matrix].sort((a,b)=>b[1]-a[1]).slice(0,25).map(([key,n])=>{const [th,to]=key.split('|');return [tax.nodes.find((t:any)=>t.id===th).label_zh,tax.nodes.find((t:any)=>t.id===to).label_zh,n]}),output);add(output,'h2','變數角色、方法與資料來源');add(output,'p',`衡量文字範圍：${a.measure_denominator_variables} 筆變數、${a.measure_denominator_papers} 篇論文。下表依全部 E3 紀錄，不受上方分類篩選影響；未知角色不推定為 IV、DV 或控制。`,'notice');table(['模型角色','紀錄數'],Object.entries(a.roles).map(([k,v])=>[labels[k]||k,v]),output);add(output,'p',Object.keys(a.methods).length?'方法欄位僅統計具來源者。':'目前估計方法尚未由來源段落確認；無法提供可信的方法分布。','muted');add(output,'p',`已辨識資料來源：${Object.entries(a.datasets).map(([k,v])=>k+' '+v+' 筆').join('；')||'未知'}。僅限衡量段落明示者，不代表資料庫使用的全面分布。`,'muted');add(output,'h2','描述性研究機會');add(output,'p','以下固定以全部索引計算，不隨上方篩選變動。僅列各主題至少10篇、合併共現至多2篇的組合；不是已驗證研究缺口。','muted');table(['主題 A','主題 B','共同篇數 / 索引分母'],a.opportunities.map((o:any)=>[tax.nodes.find((t:any)=>t.id===o.a).label_zh,tax.nodes.find((t:any)=>t.id===o.b).label_zh,`${o.joint_papers} / ${o.denominator}`]),output)}controls.addEventListener('input',render);render()}

const reasonLabels:Record<string,string>={not_reported:'充分檢查後未報告',not_found_after_search:'已搜尋，但未定位到可靠證據',not_applicable:'不適用',inaccessible_fulltext:'全文不可取得',not_parsed:'版面／表格／公式尚未成功解析',ambiguous:'無法明確判定',not_yet_processed:'尚未處理',evidence_conflict:'不同來源敘述或規格有衝突'};
function renderV4(r:any){add(app,'h2','v4 逐欄研究證據');box('每個欄位獨立定位原文；source alignment 不代表獨立評估的語意正確率。論文層級樣本／方法不會無條件套用到所有變數或模型。');add(app,'p',`Parser ${r.parser_version} · Extractor ${r.extractor_version} · ${r.variables.length} 筆變數／衡量 · ${r.models.length} 個模型 · ${r.estimates.length} 個表格估計`,'status-line');const evidence=new Map(r.evidence.map((x:any)=>[x.evidence_id,x]));function proofs(parent:Element,ids:string[]){for(const id of ids){const v:any=evidence.get(id);if(!v)continue;const d=add(parent,'details');add(d,'summary',`${v.section} · page ${v.page??'HTML'}${v.table?' · '+v.table+' row '+v.row+' col '+v.column:''}`);link(d,'開啟原始來源',v.source_url+(v.page?'#page='+v.page:''));add(d,'p',v.quoted_excerpt||'本篇短引文配額已用盡；仍保留原始位置與 hash。');add(d,'p',`block ${v.block_id}; offset ${v.start}–${v.end}; span ${v.span_hash}`,'tiny');add(d,'p',`${v.verification_status} · ${v.extraction_method} · ${v.confidence}`,'muted')}}function fieldRows(parent:Element,fields:any){table(['欄位','值／Unknown 原因','逐欄原文證據'],Object.entries(fields).map(([name,raw])=>{const f:any=raw;const cell=e('div',f.value===null?'Unknown · '+(reasonLabels[f.reason]||f.reason):typeof f.value==='object'?JSON.stringify(f.value):String(f.value));if(f.status==='inferred_not_original_formula')add(cell,'p','由文字正規化敘述推導的比率，並非原文寫出的公式。','notice');if(f.detail)add(cell,'p',f.detail,'tiny');if(f.candidates)add(cell,'p','候選／不同規格：'+JSON.stringify(f.candidates),'tiny');const ev=e('div');proofs(ev,f.evidence_ids);return [name,cell,ev]}),parent)}const theoryRows:Array<any>=r.theory_evidence||[];
const theoryScope=r.theory_search_coverage;
const theoryPanel=add(app,'details');
add(theoryPanel,'summary','全文 Theory 證據：作者明示使用 vs 章節提及 · '+theoryRows.length+' 筆');
add(theoryPanel,'p','只有作者在 Introduction / Theory / Hypotheses 相關章節明示使用某視角，才可形成全文來源的 Theory 分類。單純提及仍是候選。推論未經獨立學術語義驗證。','muted');
if(theoryScope){add(theoryPanel,'p','掃描：'+theoryScope.status+' · '+theoryScope.scoped_blocks+' 個段落；'+(theoryScope.scoped_sections||[]).join('、'),'tiny');}
if(!theoryRows.length)add(theoryPanel,'p','尚無具可對齊證據的 Theory 名稱；不代表文章未使用理論。','empty');
for(const v of theoryRows){
 const line=add(theoryPanel,'article',undefined,'record');
 add(line,'h4',v.term_id+' · '+(v.status==='author_declared_use'?'作者明示理論視角':'僅章節提及／未驗證'));
 add(line,'p','辨識詞組：'+v.matched_phrase+' · 章節：'+v.section+' · 頁碼：'+(v.page??'HTML'),'tiny');
 if((v.hypothesis_ids||[]).length)add(line,'p','同段落假設線索：'+v.hypothesis_ids.join('、')+'（並非確認因果或理論來源）','tiny');
 proofs(line,v.evidence_ids||[]);
}
const pf=add(app,'details');add(pf,'summary','論文層級：樣本、資料、方法與研究結果');fieldRows(pf,r.fields);for(const v of r.variables){const d=add(app,'details');d.id=v.variable_id;add(d,'summary',v.name+' · 各欄位與衡量規格');fieldRows(d,v.fields)}const coverage=add(app,'details');add(coverage,'summary','已搜尋範圍與解析缺口');add(coverage,'pre',JSON.stringify(r.search_coverage,null,2));for(const [label,rows] of [['假設／命題',r.hypotheses],['模型',r.models],['逐模型估計',r.estimates],['結果與假設支持',r.findings],['穩健性／敏感性程序與結果',r.checks]] as [string,any[]][]){const d=add(app,'details');add(d,'summary',label+' · '+rows.length+' 筆');for(const row of rows){const c=add(d,'article',undefined,'record');add(c,'pre',JSON.stringify(Object.fromEntries(Object.entries(row).filter(([k])=>k!=='evidence_ids')),null,2));proofs(c,row.evidence_ids)}}}

const handlers:Record<string,()=>Promise<void>>={dashboard,explorer,profile,dictionary,quality,theories,gaps,automaticQuality,analytics};
try{await handlers[app.dataset.kind!]()}catch(error){app.replaceChildren();add(app,'h1','資料暫時無法載入');add(app,'p',error instanceof Error?error.message:'未知錯誤','notice');link(app,'返回總覽',base);console.error(error)}
