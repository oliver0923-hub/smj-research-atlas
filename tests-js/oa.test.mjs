import test from 'node:test';
import assert from 'node:assert/strict';
import {DOMParser} from 'linkedom';
import {extract,segments} from '../src/scripts/oa-extract.ts';
import {safeURL,validate,htmlPages,candidatesFor,fetchSource} from '../src/scripts/browser-oa.ts';
const paper={doi:'10.1002/smj.1234',title:'Firm age and strategic performance in organizations',authors:['Alice Author']};
test('fresh CC repository candidates are usable despite submitted-version metadata',()=>{
 const raw={locations:[{is_oa:true,version:'submittedVersion',license:'cc-by-nc-nd',pdf_url:'https://www.econstor.eu/a.pdf'}]};
 assert.equal(candidatesFor(paper,raw)[0].url,'https://www.econstor.eu/a.pdf');
 assert.equal(candidatesFor(paper,{locations:[{...raw.locations[0],license:null}]}).length,0);
 assert.equal(safeURL('https://www.econstor.eu.evil.test/a'),null);
});
test('article identity cannot be satisfied by arbitrary metadata text alone',()=>{
 const text=paper.title+' Alice Author 10.1002/smj.1234 '+('methods results data observations '.repeat(90));
 assert.doesNotThrow(()=>validate(paper,[{page:1,text}]));
 assert.throws(()=>validate({...paper,doi:'10.1002/smj.9999',title:'Completely unrelated ecosystem innovation strategy',authors:['Bob Nobody']},[{page:1,text}]),/identity/);
 assert.throws(()=>validate(paper,[{page:1,text:paper.title+' Alice Author'}]),/full_article/);
});
test('substantive HTML required; long repository abstracts are rejected',()=>{
 globalThis.DOMParser=DOMParser;
 const abstract='<main><h1>'+paper.title+'</h1><h2>Abstract</h2><p>'+('metadata abstract '.repeat(200))+'</p></main>';
 assert.throws(()=>htmlPages(abstract),/metadata_landing/);
 const full='<article><h2>Methods</h2><p>We use Compustat data for the sample.</p><h2>Results</h2><p>We find support for Hypothesis 1 in this sample.</p></article>';
 assert.ok(htmlPages(full).some(p=>p.text==='Methods'));
});
test('whole-paper scan finds different fields on separate pages and preserves conflicting periods',async()=>{
 const pages=[{page:2,text:'DATA\nOur sample uses Compustat for the period 2001 to 2015.'},{page:8,text:'METHODS\nWe estimate ordinary least squares regressions.'},{page:15,text:'APPENDIX\nOur alternative sample uses CRSP for the period 2002 to 2010.'}];
 const r=await extract(paper,pages,'https://www.econstor.eu/a.pdf','pdf');
 assert.equal(r.fields.sample_period.value,null);assert.equal(r.fields.sample_period.status,'evidence_conflict');
 assert.match(r.fields.data_source.value,/Compustat/);assert.match(r.fields.data_source.value,/CRSP/);
 assert.match(r.fields.empirical_method.value,/ordinary least squares/);
 assert.equal(r.fields.empirical_method.evidence[0].page,8);
});
test('references excluded but appendices resume; no invented hypotheses or findings',async()=>{
 const pages=[{page:1,text:'REFERENCES\nWe find support for Hypothesis 9. We use Compustat data for 1980 to 1990.'},{page:2,text:'APPENDIX\nWe use CRSP data for the period 2001 to 2008.'}];
 const r=await extract(paper,pages,'https://www.econstor.eu/a.pdf','pdf');
 assert.equal(r.hypotheses.length,0);assert.equal(r.findings.length,0);
 assert.equal(r.fields.data_source.value,'CRSP');
});
test('proposals, support and significance are distinct; theory mention is not author adoption',async()=>{
 const pages=[{page:3,text:'HYPOTHESES\nHypothesis 1: Firm age is positively related to organizational performance.\nWe build on agency theory to explain organizational behavior.\nPrevious literature mentions upper echelons theory in this context.'},{page:9,text:'RESULTS\nHypothesis 1 was not supported by our results.'}];
 const r=await extract(paper,pages,'https://www.econstor.eu/a.pdf','pdf');
 assert.equal(r.hypotheses[0].kind,'proposed_hypothesis');assert.equal(r.findings[0].support_status,'not_supported');
 assert.equal(r.findings[0].significance,'unknown');
 assert.equal(r.theories.find(x=>/agency/.test(x.label)).kind,'author_use_statement');
 assert.equal(r.theories.find(x=>/upper echelons/.test(x.label)).kind,'theory_mention');
 const quoted=[...r.hypotheses,...r.findings,...r.theories,...r.robustness,...Object.values(r.fields).flatMap(f=>f.evidence||[])].reduce((n,e)=>n+(e.excerpt?e.excerpt.split(/\s+/).length:0),0);
 assert.ok(quoted<=24*48);
 for(const e of [...r.hypotheses,...r.findings,...r.theories,...r.robustness,...Object.values(r.fields).flatMap(f=>f.evidence||[])]) assert.ok(e.excerpt?.length);
});
test('downloaded bytes that fail identity are not a successful analysis',async()=>{
 const html=('<article><h2>Methods</h2><p>'+('Different study with unrelated text. '.repeat(100))+'</p><h2>Results</h2><p>We describe a different paper.</p></article>');
 const r=new Response(html,{headers:{'Content-Type':'text/html'}});
 await assert.rejects(fetchSource(paper,{url:'https://www.econstor.eu/a',kind:'html'},r),e=>/untrusted_resolved_source/.test(e.message)&&e.response_bytes>0&&e.downloaded_bytes===0);
});
test('parenthesized H labels and multiline proposals keep original text and source offsets',async()=>{
 const pages=[{page:3,text:'HYPOTHESES\nHypothesis (H1).\nFirm age is positively associated with performance.'}];
 const r=await extract(paper,pages,'https://www.econstor.eu/a.pdf','pdf');
 assert.equal(r.hypotheses[0].label,'H1');
 assert.ok(r.hypotheses[0].offset_start>=0);
 assert.match(r.hypotheses[0].excerpt,/Hypothesis \(H1\)\./);
});
test('policy treatment dates are not sample dates and discussion alternatives are not estimated methods',async()=>{
 const pages=[{page:10,text:'3 | EMPIRICAL SETTING AND DATA\nWe use a difference-in-differences methodology based on treatments occurring between 1980 and 2006.\nOur underlying data span the period between 1977 and 2011.'},{page:30,text:'6 | DISCUSSION\nFuture research could use an instrumental variable approach for our setting.'}];
 const r=await extract(paper,pages,'https://www.econstor.eu/a.pdf','pdf');
 assert.equal(r.fields.sample_period.value,'1977–2011');
 assert.equal(r.fields.empirical_method.value,'difference-in-differences');
 assert.equal(r.fields.empirical_method.evidence[0].label,'difference-in-differences');
});

test('reported support after the verb is retained and results outrank early summary matches',async()=>{
 const intro='INTRODUCTION\n'+Array.from({length:14},(_,i)=>`We find an introductory association for group ${i}.`).join('\n');
 const r=await extract(paper,[{page:1,text:intro},{page:20,text:'5 | EMPIRICAL RESULTS\nThese results broadly support Hypothesis (H2), with the stated qualifications.'}],'https://example.test/a.pdf','pdf');
 assert.equal(r.findings[0].label,'H2');assert.equal(r.findings[0].support_status,'supported');assert.equal(r.findings[0].significance,'unknown');assert.equal(r.findings[0].page,20);
});
