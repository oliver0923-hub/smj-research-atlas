"""Claims have separate inference, evidence and validation axes; no fake expert review."""
import hashlib
import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Origin=Literal['publisher_metadata','crossref_metadata','openalex_metadata','deterministic_rule','model_inference','fulltext_extraction','human_review']
Grade=Literal['E0_metadata','E1_abstract','E2_fulltext_section','E3_measurement_text']
Validation=Literal['validated_automatic','provisional','failed','insufficient_evidence']

class EvidenceClaim(BaseModel):
    inference_origin: Origin
    evidence_grade: Grade
    validation_status: Validation
    source_url: str
    evidence_locator: str
    source_hash: str
    heuristic_score: float | None = Field(default=None,ge=0,le=1)
    algorithm_version: str
    retrieved_at: str
    missing_reason: dict[str,str] = Field(default_factory=dict)

class OperationalVariable(EvidenceClaim):
    variable_id: str
    paper_id: str
    variable_label_original: str
    construct_en: str
    construct_zh: str | None = None
    role: Literal['independent','dependent','mediator','moderator','control','instrument','selection','other','unknown']='unknown'
    operational_definition: str | None = None
    proxy_name: str | None = None
    formula: str | None = None
    formula_source_text: str | None = None
    unit: str | None = None
    lag: str | None = None
    sample_period: str | None = None
    data_source: str | None = None
    empirical_method: str | None = None
    reported_association: str | None = None
    source_page: int | None = None
    source_span_start: int
    source_span_end: int
    span_hash: str
    evidence_excerpt: str
    verification_status: str='fulltext_screened'
    extraction_method: str='deterministic_measurement_span_v1'
    human_reviewer: str | None = None
    field_evidence: dict[str,str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def consistency(self):
        if self.evidence_grade!='E3_measurement_text':raise ValueError('Variable measures require actual measurement text')
        if self.inference_origin not in {'fulltext_extraction','human_review'}:raise ValueError('Title or abstract cannot yield variable measurements')
        if self.source_span_end<=self.source_span_start or not self.evidence_excerpt:raise ValueError('Source span required')
        if len(self.evidence_excerpt.split())>24:raise ValueError('Excerpt budget exceeded')
        if self.formula and (not self.formula_source_text or self.formula!=self.formula_source_text):raise ValueError('Formula must match original formula text')
        for field in ['formula','unit','lag','sample_period','data_source','empirical_method','reported_association']:
            if getattr(self,field) is None and field not in self.missing_reason:raise ValueError('Unknown field needs explicit missing_reason')
        for field in ['lag','sample_period','data_source','empirical_method','reported_association']:
            if getattr(self,field) is not None and (not self.field_evidence.get(field) or self.field_evidence[field] not in self.evidence_excerpt):raise ValueError('Field lacks matching source text: '+field)
        if self.role!='unknown' and not self.field_evidence.get('role'):raise ValueError('Model role requires explicit source evidence')
        return self

EXTRACTION_VERSION='measurement-span-v2-multi'

PATTERNS=[
 re.compile(r'\b(?:We|we)\s+(?:measured?|operationalized?)\s+(?:the\s+)?(?P<name>[A-Za-z][A-Za-z \-]{2,55}?)\s+(?:as|by|using|with)\s+(?P<definition>[^.!?]{12,210})'),
 re.compile(r'\b(?P<name>[A-Z][A-Za-z \-]{2,55}?)\s+(?:was|is|were|are)\s+(?:measured|operationalized|computed|calculated)\s+(?:as|by|using)\s+(?P<definition>[^.!?]{12,210})'),
 re.compile(r'\b(?:We|we)\s+(?:defined?|constructed?|computed|calculated)\s+(?:the\s+)?(?P<name>[A-Za-z][A-Za-z \-]{2,55}?)\s+(?:as|by|using)\s+(?P<definition>[^.!?]{12,210})'),
 re.compile(r'\b(?P<name>[A-Z][A-Za-z \-]{2,55}?)\s+(?:was|is|were|are)\s+(?:defined|constructed|coded)\s+(?:as|by|using)\s+(?P<definition>[^.!?]{12,210})')]

def measurement_details(span):
    """Narrow text-to-field rules; no general construct definition is imputed."""
    text=span.lower().replace('num- ber','number')
    if 'patent applications' in text and 'normalized by the number of new entrants' in text:
        return dict(proxy_name='按新進企業數標準化的專利申請數',operational_definition='以某州某年新申請人提交的專利申請數，按新進企業數標準化，代理新創品質。',numerator='新申請人之專利申請數',denominator='新進企業數',level_of_analysis='state-year')
    if 'return on equity' in text and 'asset4' in text:
        return dict(proxy_name='ROE',operational_definition='以股東權益報酬率衡量企業績效；該句明確指出資料取自 ASSET4。',data_source='ASSET4')
    if 'cumulative revenue in eur' in text:
        return dict(proxy_name='累計營收',unit='EUR',operational_definition='自訓練開始累計至各試驗最後可用觀察時點的企業營收，以歐元計。')
    if 'number of years' in text and 'wage employment or new venture' in text:
        return dict(proxy_name='任職年數',unit='years',operational_definition='受訪者在特定受僱工作或新創事業中已任職的年數。')
    if 'maximum number of patents' in text and 'single technology class' in text:
        return dict(proxy_name='單一技術類別之專利數最大值',unit='patents',level_of_analysis='inventor',operational_definition='以發明人在原文所指的同一五年期間、單一技術類別內成功申請的專利數最大值衡量知識深度。該句未明確界定此期間的起訖年份。')
    if 'five-item' in text and 'scale' in text:
        return dict(proxy_name='五題量表',operational_definition='使用原文所引量表的精簡五題版本；該句未提供各題、計分方式或完整信效度資訊。')
    if 'aggregation of the individual-level engagement data' in text:
        return dict(proxy_name='個人投入資料之群體彙整',level_of_analysis='group',operational_definition='將個人層級投入資料彙整為群體層級投入；此句未具體交代使用平均或其他彙整規則。')
    return {}

def extract_variables(paper,pages,receipt):
    """Return every distinct source-aligned named measure across the paper.

    This conservative extractor does not claim exhaustive variable coverage.
    """
    if not receipt.get('accessible'):return []
    found=[]
    seen=set()
    for page in pages:
        text=' '.join(page['text'].split())
        for pattern in PATTERNS:
            for match in pattern.finditer(text):
                name=match['name'].strip();definition=match['definition'].strip()
                if any(w in name.lower().split() for w in ['this','these','those','which','it','we','our','were','was']) or len(name.split())>7:continue
                context=text[max(0,match.start()-1800):match.end()+500]
                if not re.search(r'\b(measures|measurement|variables|dependent variable|independent variable)\b',context,re.I):continue
                span=text[match.start():match.end()]
                # Public evidence is bounded. Full source text stays only in ignored transient cache.
                excerpt=' '.join(span.split()[:20])
                key=paper['paper_id']+'|'+' '.join(name.lower().split())
                if key in seen:continue
                record=OperationalVariable(variable_id='var:'+hashlib.sha256(key.encode()).hexdigest()[:20],paper_id=paper['paper_id'],
                    variable_label_original=name,construct_en=name,operational_definition='依原文以「'+definition[:160]+'」描述衡量；僅通過來源文字對齊，未經專家審閱。',
                    inference_origin='fulltext_extraction',evidence_grade='E3_measurement_text',validation_status='validated_automatic',
                    source_url=receipt['source_url'],evidence_locator=('PDF page '+str(page['page']) if page['page'] else 'HTML measurement paragraph')+'; normalized characters '+str(match.start())+'–'+str(match.end()),
                    source_hash=receipt['source_hash'],algorithm_version=EXTRACTION_VERSION,retrieved_at=receipt['checked_at'],
                    source_page=page['page'],source_span_start=match.start(),source_span_end=match.end(),span_hash=hashlib.sha256(span.encode()).hexdigest(),evidence_excerpt=excerpt,
                    missing_reason={k:'not_verified_from_aligned_measurement_span' for k in ['formula','unit','lag','sample_period','data_source','empirical_method','reported_association','construct_zh','role','proxy_name']})
                # Keep the operational definition a paraphrase with a short source locator, not a long quote.
                result=record.model_dump();result['operational_definition']='原文將 '+name+' 與指定的衡量程序連結；完整定義請見所附原始頁碼／段落。'
                result.update(measurement_details(span))
                # Explicit field evidence must be present in the bounded excerpt.
                for field in ('unit','lag','sample_period','data_source','empirical_method','reported_association'):
                    value=result.get(field)
                    if value is None:continue
                    token=str(value)
                    pos=result['evidence_excerpt'].lower().find(token.lower())
                    if pos>=0:
                        result['field_evidence'][field]=result['evidence_excerpt'][pos:pos+len(token)]
                        result['missing_reason'].pop(field,None)
                    else:
                        result[field]=None
                        result['missing_reason'][field]='not_verifiable_in_bounded_excerpt'
                verify_span(result,pages)
                result['alignment_verified']=True
                OperationalVariable.model_validate(result)
                found.append(result)
                seen.add(key)
    return found

def verify_span(record,pages):
    page=next((p for p in pages if p['page']==record['source_page']),None)
    if page is None:raise ValueError('Source page missing')
    text=' '.join(page['text'].split());span=text[record['source_span_start']:record['source_span_end']]
    if hashlib.sha256(span.encode()).hexdigest()!=record['span_hash']:raise ValueError('Source-span hash mismatch')
    if record['evidence_excerpt']!=' '.join(span.split()[:20]):raise ValueError('Evidence does not align with source span')
    if record.get('formula') and record['formula'] not in span:raise ValueError('Formula absent from original span')
    return True
