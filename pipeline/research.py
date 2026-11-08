"""Paper-wide deterministic extraction with independently located field evidence.

Known means source-grounded extraction, not an expert semantic certification.
Unknowns are intentionally first-class data. No fabricated statistical results.
"""
import hashlib
import re
from collections import Counter, defaultdict
from .article import ArticleDocument, digest, norm
from .study import finding_status, robustness_status, LABEL, INTRO, tag, sentences

EXTRACTOR_VERSION='research-fields-4.0'
MISSING={'not_reported','not_found_after_search','not_applicable','inaccessible_fulltext',
         'not_parsed','ambiguous','not_yet_processed','evidence_conflict'}
VARIABLE_FIELDS=['construct','proxy','role','operational_definition','formula','inferred_ratio',
    'numerator','denominator','scale','unit','level_of_analysis','aggregation','lag','lead',
    'measurement_window','temporal_alignment','sample_period','sample_unit','sample_country',
    'sample_industry','sample_size','data_source','collection_method','empirical_method',
    'estimator','fixed_effects','model_specification','controls','reported_relation',
    'significance','robustness','sensitivity']
PAPER_FIELDS=['hypotheses','propositions','sample_period','sample_unit','sample_country',
    'sample_industry','sample_size','data_source','collection_method','empirical_method',
    'estimator','fixed_effects','model_specification','findings','significance','robustness','sensitivity']
DATABASES=re.compile(r'\b(Compustat|CRSP|ASSET4|BoardEx|Orbis|Worldscope|SDC(?: Platinum)?|Revelio|PATSTAT|USPTO|COMPUSTAT|CompuStat|LexisNexis|Factiva|Thomson Reuters|Bureau van Dijk)\b',re.I)
METHODS=re.compile(r'\b(ordinary least squares|OLS|two[- ]stage least squares|2SLS|logit|logistic regression|probit|Poisson|negative binomial|Cox proportional hazards?|hazard model|difference[- ]in[- ]differences|generalized method of moments|GMM|fixed[- ]effects? regressions?|structural equation model(?:ing)?|qualitative comparative analysis|randomized controlled trial|instrumental variables?|fuzzy[- ]set qualitative comparative analysis)\b',re.I)
ROLE_PATTERNS={'dependent':r'dependent variables?|outcome variables?', 'independent':r'independent variables?|explanatory variables?',
    'moderator':r'moderat(?:or|ing) variables?', 'mediator':r'mediat(?:or|ing) variables?',
    'control':r'control variables?', 'instrument':r'instrumental variables?', 'selection':r'selection variables?'}
DEFINITIONS=[
 re.compile(r'\b(?:we|We)\s+(?:measure[ds]?|operationalize[ds]?|define[ds]?|construct(?:ed)?|calculate[ds]?|compute[ds]?|code[ds]?)\s+(?:the\s+)?(?P<name>[A-Za-z][A-Za-z0-9 /()\-]{2,70}?)\s+(?:as|by|using|with)\s+(?P<definition>[^.!?]{10,350})'),
 re.compile(r'\b(?P<name>[A-Z][A-Za-z0-9 /()\-]{2,70}?)\s+(?:is|was|are|were)\s+(?:measured|operationalized|defined|constructed|computed|calculated|coded)\s+(?:as|by|using|with)\s+(?P<definition>[^.!?]{10,350})'),
 re.compile(r'\b(?:dependent|independent|control|moderator|mediator) variable[,]?\s+(?P<name>[A-Za-z][A-Za-z0-9 \-]{2,45}?)[,:]\s+(?:is|was)\s+(?P<definition>[^.!?]{10,250})',re.I)]


def evidence_integrity(e):
    return digest('|'.join(str(e.get(k)) for k in ['paper_id','source_url','source_hash','block_id','block_hash','start','end','span_hash','quote_hash','table','row','column']))


def key(value):
    return re.sub(r'[^a-z0-9]+',' ',value.lower()).strip()


def unknown(reason='not_found_after_search', detail='No unambiguous source-aligned value found in inspected blocks'):
    return dict(value=None,status='unknown',reason=reason,detail=detail,evidence_ids=[])


class EvidenceRegistry:
    def __init__(self,doc,quote_budget=200):
        self.doc=doc;self.rows={};self.words=quote_budget

    def add(self,block,start=0,end=None,method='explicit_text_rule',confidence='rule_based_uncalibrated'):
        end=len(block['text']) if end is None else end
        span=block['text'][start:end]
        if not span or start<0 or end>len(block['text']):raise ValueError('Invalid evidence span')
        ident='ev:'+digest(self.doc.paper_id+'|'+self.doc.source_hash+'|'+block['block_id']+'|'+str(start)+'|'+str(end))[:24]
        if ident not in self.rows:
            words=span.split()[:min(12,self.words)];self.words-=len(words)
            excerpt=' '.join(words)
            self.rows[ident]=dict(evidence_id=ident,paper_id=self.doc.paper_id,source_url=self.doc.source_url,
                source_hash=self.doc.source_hash,section=block['section'],page=block['page'],block_id=block['block_id'],
                table=block.get('table'),row=block.get('row'),column=block.get('column'),bbox=block.get('bbox'),
                equation=block['block_id'] if block['kind']=='equation' else None,
                start=start,end=end,span_hash=digest(span),block_hash=block['block_hash'],quoted_excerpt=excerpt,
                quote_hash=digest(excerpt),quotation_status='bounded_excerpt' if excerpt else 'paper_quotation_budget_exhausted',
                extraction_method=method,confidence=confidence,verification_status='source_span_aligned',
                parser_version=self.doc.parser_version,extractor_version=EXTRACTOR_VERSION)
            self.rows[ident]['alignment_digest']=evidence_integrity(self.rows[ident])
        return ident

    def validate(self):
        blocks={b['block_id']:b for b in self.doc.blocks}
        for e in self.rows.values():
            b=blocks[e['block_id']];span=b['text'][e['start']:e['end']]
            if digest(span)!=e['span_hash'] or b['block_hash']!=e['block_hash']:raise ValueError('Source hash/offset mismatch')
            if e['quoted_excerpt'] and not span.lstrip().startswith(e['quoted_excerpt']):raise ValueError('Quote not aligned')
        return True


def assign(fields,name,value,ev,scope='explicit_statement',status='source_grounded'):
    if name not in fields:fields[name]=unknown()
    if value is None or value=='':return
    old=fields[name]
    if old['value'] is not None and old['value']!=value:
        candidates=old.get('candidates',[old['value']])
        if value not in candidates:candidates.append(value)
        fields[name]=dict(value=None,status='unknown',reason='evidence_conflict',detail='Multiple non-equivalent reported values/specifications',
                          candidates=candidates,evidence_ids=list(dict.fromkeys(old['evidence_ids']+[ev])),scope=scope)
    elif old.get('reason')=='evidence_conflict':
        if value not in old['candidates']:old['candidates'].append(value)
        old['evidence_ids']=list(dict.fromkeys(old['evidence_ids']+[ev]))
    else:
        fields[name]=dict(value=value,status=status,reason=None,evidence_ids=list(dict.fromkeys(old.get('evidence_ids',[])+[ev])),scope=scope)


def assign_many(fields,name,value,ev,scope='paper_context'):
    old=fields[name]
    values=list(old['value']) if isinstance(old.get('value'),list) else [old['value']] if old.get('value') is not None else []
    if value not in values:values.append(value)
    fields[name]=dict(value=values,status='source_grounded',reason=None,evidence_ids=list(dict.fromkeys(old.get('evidence_ids',[])+[ev])),scope=scope)


def usable(block):
    return not re.search(r'^(references|bibliography)',block['section'],re.I)


def extraction(doc):
    registry=EvidenceRegistry(doc)
    fields={k:unknown() for k in PAPER_FIELDS};variables=[];seen=set()
    blocks=[b for b in doc.blocks if usable(b)]
    methods_blocks=[b for b in blocks if re.search(r'method|data|sample|measure|variable|research design|appendi',b['section']) or re.search(r'\b(?:our|we|the final|the estimation) (?:sample|data|use|employ|estimate|collected)\b',b['text'],re.I)]
    # If no heading survived, search prose but still require explicit measurement verbs.
    candidates=[b for b in blocks if b['kind'] in {'paragraph','equation'}]
    for b in candidates:
        for pattern in DEFINITIONS:
            for m in pattern.finditer(b['text']):
                name=m['name'].strip(' ,:().');definition=m['definition'].strip()
                if len(name.split())>8 or re.search(r'\b(this|these|those|which|whether|we|our|their|was|were)\b',name,re.I):continue
                # Preserve alternative definitions rather than collapsing by variable name.
                signature=key(name)+'|'+key(definition)
                if signature in seen:continue
                seen.add(signature);ev=registry.add(b,m.start(),m.end(),'explicit_measurement_definition')
                v=dict(variable_id='var4:'+digest(doc.paper_id+'|'+signature)[:24],paper_id=doc.paper_id,name=name,
                       construct_id='construct:'+digest(key(name))[:16],model_id=None,
                       fields={k:unknown() for k in VARIABLE_FIELDS})
                assign(v['fields'],'construct',name,ev,'author_variable_label_not_standardized_construct')
                assign(v['fields'],'operational_definition','原文將 '+name+' 與此來源段落中的衡量程序連結。',ev)
                # Literal short proxy component, never a reconstructed formula.
                proxy=re.search(r'\bproxied by\s+(?P<value>[^;]{5,250})',definition,re.I)
                if proxy:
                    a,z=proxy.span('value')
                    assign(v['fields'],'proxy',proxy['value'].strip(),registry.add(b,m.start('definition')+a,m.start('definition')+z))
                else:
                    # A ratio denominator must never become the proxy simply because its noun matches.
                    before_divisor=re.split(r'\b(?:normalized|divided) by\b',definition,flags=re.I)[0]
                    proxy=re.search(r'\b(number of [a-z -]{3,55}|return on (?:equity|assets)|[a-z-]*item (?:scale|measure)|cumulative revenue)\b',before_divisor,re.I)
                    if proxy:assign(v['fields'],'proxy',proxy[0].strip(),registry.add(b,m.start('definition')+proxy.start(),m.start('definition')+proxy.end()))
                ratio=re.search(r'(?P<num>[^;]{5,160}?)\s+(?:normalized|divided) by\s+(?P<den>[^;.]{5,120})',definition,re.I)
                if ratio:
                    num=ratio['num'].strip();den=ratio['den'].strip()
                    assign(v['fields'],'numerator',num,ev);assign(v['fields'],'denominator',den,ev)
                    assign(v['fields'],'inferred_ratio',dict(numerator=num,denominator=den),ev,'verbal_normalization_only','inferred_not_original_formula')
                variables.append(v)
    # Table variable dictionaries provide additional measurement definitions.
    by_table=defaultdict(list)
    for b in blocks:
        if b['kind']=='table_cell':by_table[b['table']].append(b)
    for table,cells in by_table.items():
        rows=defaultdict(dict)
        for b in cells:rows[b['row']][b['column']]=b
        if not rows:continue
        headers={c:b['text'].lower() for c,b in rows.get(0,{}).items()}
        definition_cols=[c for c,t in headers.items() if re.search('definition|measurement|description',t)]
        name_cols=[c for c,t in headers.items() if re.search('variable|construct|measure',t) and c not in definition_cols]
        if not definition_cols or not name_cols:continue
        for ri,row in sorted(rows.items()):
            if ri==0 or name_cols[0] not in row or definition_cols[0] not in row:continue
            n=row[name_cols[0]];d=row[definition_cols[0]];signature=key(n['text'])+'|'+key(d['text'])
            if signature in seen:continue
            seen.add(signature);ev=registry.add(d,method='table_definition_cell')
            v=dict(variable_id='var4:'+digest(doc.paper_id+'|'+signature)[:24],paper_id=doc.paper_id,name=n['text'],construct_id='construct:'+digest(key(n['text']))[:16],model_id=None,fields={k:unknown() for k in VARIABLE_FIELDS})
            assign(v['fields'],'construct',n['text'],registry.add(n),'author_variable_label_not_standardized_construct')
            assign(v['fields'],'operational_definition','原文表格定義 '+n['text']+' 的衡量方式，詳見定位儲存格。',ev)
            variables.append(v)
    # Paper/sample facts are explicitly paper-scoped; disagreement remains ambiguous.
    for b in methods_blocks:
        if b['kind']=='heading':continue
        text=b['text']
        for m in DATABASES.finditer(text):assign_many(fields,'data_source',m[0],registry.add(b,m.start(),m.end()),'paper_data_section')
        if re.search(r'\b(use[ds]?|employ\w*|estimat\w*|implement\w*|fit|apply|applied)\b',text,re.I):
            for m in METHODS.finditer(text):
                ev=registry.add(b,max(0,m.start()-70),min(len(text),m.end()+70))
                assign_many(fields,'empirical_method',m[0],ev,'paper_methods_section');assign_many(fields,'estimator',m[0],ev,'paper_methods_section')
        for m in re.finditer(r'\b(?:from|between|during|over|period(?: of)?)\s+(?P<a>(?:19|20)\d{2})\s*(?:to|and|through|[-–—])\s*(?P<b>(?:19|20)\d{2})\b',text,re.I):
            a,z=int(m['a']),int(m['b'])
            if a<=z and re.search(r'sample|data|observ|period|panel|collect',text,re.I):assign(fields,'sample_period',[a,z],registry.add(b,m.start(),m.end()),'paper_sample_candidate')
        for m in re.finditer(r'\b(\d[\d,]*)\s+(firm[- ]years?|observations?|respondents?|participants?|firms?|companies|individuals?)\b',text,re.I):
            if re.search(r'sample|final|contains?|consists?|observations?|collected',text,re.I):
                ev=registry.add(b,m.start(),m.end());assign(fields,'sample_size',int(m[1].replace(',','')),ev,'paper_sample_candidate');assign(fields,'sample_unit',m[2],ev,'paper_sample_candidate')
        if re.search(r'sample|firms|companies|data|observations',text,re.I):
            for m in re.finditer(r'\b(United States|United Kingdom|China|Germany|Japan|Taiwan|India|Sweden|France|Canada|U\.S\.)',text,re.I):assign_many(fields,'sample_country',m[0],registry.add(b,m.start(),m.end()),'paper_sample_context')
            for m in re.finditer(r'\b(manufacturing|banking|pharmaceutical|biotechnology|semiconductor|software|insurance|retail) (?:industry|industries|sector|firms|companies)\b',text,re.I):assign_many(fields,'sample_industry',m[0],registry.add(b,m.start(),m.end()),'paper_sample_context')
        for m in re.finditer(r'\b((?:firm|year|industry|country|individual|state|time|month|quarter)(?:\s+and\s+(?:firm|year|industry|country|time))? fixed effects)\b',text,re.I):assign_many(fields,'fixed_effects',m[1],registry.add(b,m.start(),m.end()),'paper_model_candidate')
        for m in re.finditer(r'\b(survey|interviews?|archival data|field experiment|randomized experiment|questionnaire)\b',text,re.I):assign_many(fields,'collection_method',m[0],registry.add(b,m.start(),m.end()),'paper_method_candidate')
    for v in variables:
        vf=v['fields'];name=v['name'];name_re=re.escape(name)
        relevant=[b for b in blocks if re.search(r'(?<!\w)'+name_re+r'(?!\w)',b['text'],re.I)]
        for b in relevant:
            text=b['text'];ev=None
            def whole():return registry.add(b,method='variable_named_context')
            for role,pattern in ROLE_PATTERNS.items():
                if re.search(r'(?:'+pattern+r')[,: ]+(?:the )?'+name_re+r'\b|\b'+name_re+r'\b.{0,35}(?:'+pattern+r')',text,re.I):assign(vf,'role',role,whole(),'explicit_named_role')
                elif re.fullmatch(pattern,b['section'],re.I):assign(vf,'role',role,whole(),'explicit_subsection_scope')
            # Units and timing require the named variable in the same source block.
            for field,pattern in [('unit',r'\b(?:in|expressed in|denominated in) (USD|EUR|years|months|days|dollars|percent|percentage points)\b'),
                ('lag',r'\b(?:lagged|lag)\s+(?:by|of)?\s*(one|two|three|\d+)\s*[- ]?(years?|months?|quarters?)\b'),
                ('lead',r'\b(?:lead|led)\s+(?:by|of)?\s*(one|two|\d+)\s*[- ]?(years?|months?)\b'),
                ('measurement_window',r'\b(?:over|during|within|previous|preceding|prior|same)\s+(?:a |the )?(?:one|two|three|four|five|\d+)[- ]years?(?: period| window)?\b'),
                ('level_of_analysis',r'\b(firm[- ]year|state[- ]year|individual[- ]level|group[- ]level|team[- ]level|inventor[- ]level|country[- ]year)\b'),
                ('aggregation',r'\b(?:aggregat\w*|averag\w*|summ\w*)\b[^.;]{0,90}'),
                ('scale',r'\b(?:\d+|three|four|five|six|seven)[- ](?:item|point) (?:Likert[- ]type )?scale\b')]:
                for m in re.finditer(pattern,text,re.I):
                    local=next((t for a,z,t in sentences(text) if a<=m.start()<z),text if len(text)<250 else '')
                    if re.search(r'(?<!\w)'+name_re+r'(?!\w)',local,re.I):assign(vf,field,m[0],registry.add(b,m.start(),m.end()),'same_named_variable_sentence')
            # An original formula must literally occur; verbal normalization stays separate.
            for m in re.finditer(r'(?<!\w)'+name_re+r'\s*=\s*[^.;]{2,140}',text,re.I):assign(vf,'formula',m[0],registry.add(b,m.start(),m.end()),'original_written_formula')
            for m in DATABASES.finditer(text):
                if b in methods_blocks:assign_many(vf,'data_source',m[0],registry.add(b,m.start(),m.end()),'same_named_variable_block')
        # Paper-level method/sample context is not silently assigned to each variable/model.
        for k in ['sample_period','sample_unit','sample_country','sample_industry','sample_size','empirical_method','estimator','fixed_effects']:
            vf[k]['detail']='Paper-level candidates are separate; variable/model applicability not established'
        if vf['formula']['value'] is None and doc.gaps:vf['formula']=unknown('not_parsed','No aligned formula found; image/unruled-layout gaps prevent not_reported inference')
    hypotheses=[];findings=[];checks=[];models=[];estimates=[]
    hmap={}
    for b in blocks:
        if b['kind'] not in {'paragraph','equation'}:continue
        for start,end,text in sentences(b['text']):
            labels={tag(m[0]) for m in LABEL.finditer(text)}
            ev=None;intro=INTRO.search(text)
            if intro and intro.start()<25 and len(labels)==1:
                label=next(iter(labels));ev=registry.add(b,start,end,'labeled_theoretical_statement')
                ident='h4:'+digest(doc.paper_id+'|'+label)[:24]
                if label not in hmap:
                    row=dict(hypothesis_id=ident,label=label,kind='hypothesis' if label.startswith('H') else 'proposition',
                        summary='作者於來源位置提出 '+label+'；完整命題請參照原文。',
                        variable_ids=[v['variable_id'] for v in variables if key(v['name']) in key(text)],evidence_ids=[ev])
                    hypotheses.append(row);hmap[label]=ident
            elif not labels and re.search(r'theor|hypothes|proposition',b['section'],re.I) and re.search(r'\bwe (?:propose|hypothesize|expect|predict) that\b',text,re.I):
                ev=registry.add(b,start,end,'unlabeled_theoretical_statement_candidate')
                hypotheses.append(dict(hypothesis_id='h4:'+digest(doc.paper_id+'|'+b['block_id']+'|'+str(start))[:24],label=None,kind='proposition',summary='作者於此位置提出未編號的理論預期；保留候選狀態。',variable_ids=[v['variable_id'] for v in variables if key(v['name']) in key(text)],evidence_ids=[ev],validation_status='provisional'))
            elif len(labels)==1 and re.search(r'support|confirm|significant|p\s*[<=>]',text,re.I):
                label=next(iter(labels));support,sig=finding_status(text)
                if support!='unknown' or sig!='unknown':
                    ev=registry.add(b,start,end,'explicit_hypothesis_result_sentence')
                    findings.append(dict(finding_id='f4:'+digest(doc.paper_id+'|'+b['block_id']+'|'+str(start))[:24],hypothesis_label=label,
                        hypothesis_id=None,model_id=None,variable_ids=[],reported_support=support,
                        significance=sig,coefficient=None,p_value=None,direction=None,evidence_ids=[ev],
                        limitation='Explicit sentence only; no coefficient/model linkage imputed'))
            for kind,pattern in [('robustness',r'robustness|results? remain robust|alternative (?:measures?|specifications?)|endogeneity|instrumental variable|placebo|subsample'),('sensitivity',r'sensitivity|sensitive to|exclusion test')]:
                if re.search(pattern,text,re.I) and re.search(r'use[ds]?|estimate|perform|conduct|test|check|results?|analysis',text,re.I):
                    ev=registry.add(b,start,end,'explicit_check_statement')
                    checks.append(dict(check_id='c4:'+digest(doc.paper_id+'|'+kind+'|'+b['block_id']+'|'+str(start))[:24],kind=kind,
                        test_summary='作者在此段落討論 '+kind+' 相關程序。',result=robustness_status(text),
                        model_ids=[],hypothesis_ids=[hmap[l] for l in labels if l in hmap],evidence_ids=[ev],
                        result_reason='explicit_local_statement_only' if robustness_status(text)!='unknown' else 'not_found_after_search'))
    for f in findings:f['hypothesis_id']=hmap.get(f['hypothesis_label'])
    # Regression tables: preserve each model/cell, stars and thresholds independently.
    for table,cells in by_table.items():
        headers=cells[0].get('headers',[])
        columns={i:h for i,h in enumerate(headers) if re.fullmatch(r'(?:Model\s*)?\(?\d+\)?',h,re.I)}
        if not columns:continue
        table_rows=defaultdict(dict)
        for b in cells:table_rows[b['row']][b['column']]=b
        for col,label in columns.items():
            model_id='model:'+digest(doc.paper_id+'|'+table+'|'+str(col))[:24]
            header=next((b for b in cells if b['row']==0 and b['column']==col),None)
            if not header:continue
            models.append(dict(model_id=model_id,table=table,column=col,label=label,dv_id=None,estimator=None,evidence_ids=[registry.add(header,method='model_header_cell')]))
            for row,rcells in table_rows.items():
                if row==0 or 0 not in rcells or col not in rcells:continue
                name=rcells[0]['text'];cell=rcells[col]
                m=re.fullmatch(r'([−-]?\d+(?:\.\d+)?)(\*{0,3})(?:\s*\(([\d.]+)\))?',cell['text'])
                if not m:continue
                matches=[v for v in variables if key(v['name'])==key(name)]
                estimates.append(dict(estimate_id='estimate:'+digest(model_id+'|'+str(row))[:24],model_id=model_id,
                    variable_id=matches[0]['variable_id'] if len(matches)==1 else None,variable_label=name,
                    reported_estimate=float(m[1].replace('−','-')),coefficient=None,
                    estimate_type='unknown_without_model_scale',reported_stars=m[2] or None,
                    standard_error=None,parenthesized_statistic=float(m[3]) if m[3] else None,standard_error_status='ambiguous_parenthesized_number_type',
                    p_value=None,significance='unknown',hypothesis_support='unknown',hypothesis_id=None,
                    evidence_ids=[registry.add(cell,method='reported_numeric_table_cell'),registry.add(rcells[0])]))
    for k,rows in [('hypotheses',[h for h in hypotheses if h['kind']=='hypothesis']),('propositions',[h for h in hypotheses if h['kind']=='proposition']),('findings',findings),('robustness',[c for c in checks if c['kind']=='robustness']),('sensitivity',[c for c in checks if c['kind']=='sensitivity'])]:
        if rows:fields[k]=dict(value=len(rows),status='source_grounded',reason=None,evidence_ids=list(dict.fromkeys(e for r in rows for e in r['evidence_ids'])),scope='paper_extracted_records')
    sigrows=[r for r in findings if r['significance']!='unknown']
    if sigrows:fields['significance']=dict(value=len(sigrows),status='source_grounded',reason=None,evidence_ids=[e for r in sigrows for e in r['evidence_ids']],scope='explicit_finding_sentences_only')
    registry.validate()
    record=dict(schema_version='4.0.0',paper_id=doc.paper_id,source_url=doc.source_url,source_hash=doc.source_hash,
        parser_version=doc.parser_version,extractor_version=EXTRACTOR_VERSION,identity=doc.identity,
        fields=fields,variables=variables,hypotheses=hypotheses,models=models,estimates=estimates,findings=findings,checks=checks,
        evidence=list(registry.rows.values()),search_coverage=doc.coverage(),
        extraction_state='extraction_partial' if doc.gaps else 'extraction_complete_for_available_evidence',
        article_type='empirical_or_unresolved' if variables or models else 'article_type_unresolved',
        validation_status='source_alignment_passed_not_semantic_certification')
    validate_record(record)
    return record


def validate_record(record):
    if record.get('human_reviewer'):raise ValueError('Automatic research cannot fabricate human review')
    if record['schema_version']!='4.0.0':raise ValueError('Wrong research schema')
    evidence={e['evidence_id']:e for e in record['evidence']}
    if len(evidence)!=len(record['evidence']):raise ValueError('Duplicate evidence ID')
    for e in evidence.values():
        if e.get('alignment_digest') and e['alignment_digest']!=evidence_integrity(e):raise ValueError('Evidence integrity mismatch')
        if e['paper_id']!=record['paper_id'] or e['source_hash']!=record['source_hash'] or e['source_url']!=record['source_url']:raise ValueError('Cross-source evidence mismatch')
        if e['end']<=e['start'] or digest(e['quoted_excerpt'])!=e['quote_hash']:raise ValueError('Evidence offset or hash invalid')
        if e['table'] and (e['row'] is None or e['column'] is None):raise ValueError('Table-cell locator required')
    if set(record['fields'])!=set(PAPER_FIELDS):raise ValueError('Incomplete paper field search inventory')
    for v in record['variables']:
        if set(v['fields'])!=set(VARIABLE_FIELDS):raise ValueError('Incomplete variable field inventory')
    groups=[record['fields']]+[v['fields'] for v in record['variables']]
    for fields in groups:
        for name,f in fields.items():
            if f['value'] is None and f.get('reason') not in MISSING:raise ValueError('Missing field needs reason: '+name)
            if f['value'] is not None and not f['evidence_ids']:raise ValueError('Known field has no evidence: '+name)
            if any(i not in evidence for i in f['evidence_ids']):raise ValueError('Dangling field evidence')
    hypotheses={h['hypothesis_id'] for h in record['hypotheses']};models={m['model_id'] for m in record['models']};variables={v['variable_id'] for v in record['variables']}
    for f in record['findings']:
        if f['hypothesis_id'] and f['hypothesis_id'] not in hypotheses:raise ValueError('Dangling hypothesis link')
        if f['model_id'] and f['model_id'] not in models:raise ValueError('Dangling model link')
    for e in record['estimates']:
        if e['model_id'] not in models or (e['variable_id'] and e['variable_id'] not in variables):raise ValueError('Dangling estimate link')
    for rows in [record['hypotheses'],record['models'],record['estimates'],record['findings'],record['checks']]:
        for row in rows:
            if any(i not in evidence for i in row['evidence_ids']):raise ValueError('Dangling relational evidence')
    return True


def report(records,total_papers):
    n=len(records);vs=[v for r in records for v in r['variables']]
    def coverage(groups,names):
        return {k:dict(known=sum(g[k]['value'] is not None for g in groups),denominator=len(groups),
            coverage=sum(g[k]['value'] is not None for g in groups)/len(groups) if groups else None,
            missing_reasons=dict(Counter(g[k].get('reason') for g in groups if g[k]['value'] is None))) for k in names}
    return dict(schema_version='4.0.0',parsed_papers=n,indexed_denominator=total_papers,variable_records=len(vs),
        paper_fields=coverage([r['fields'] for r in records],PAPER_FIELDS),variable_fields=coverage([v['fields'] for v in vs],VARIABLE_FIELDS),
        hypotheses=sum(len(r['hypotheses']) for r in records),models=sum(len(r['models']) for r in records),
        estimates=sum(len(r['estimates']) for r in records),findings=sum(len(r['findings']) for r in records),
        checks=sum(len(r['checks']) for r in records),accuracy=None,accuracy_reason='See independent evaluation; alignment is not semantic accuracy')
