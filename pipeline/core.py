"""Source-grounded metadata normalization. No full-text or measure inference."""
import re
import html
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator

ISSNS = {'1097-0266', '0143-2095'}
STATUSES = {'metadata_only', 'abstract_screened', 'fulltext_screened', 'measurement_verified', 'human_reviewed'}
def display_text(value):
    """Decode publisher formatting without interpreting markup in the browser."""
    return html.unescape(re.sub(r"<[^>]+>", "", value))

def now(): return datetime.now(timezone.utc).isoformat()
def doi_key(value):
    value = re.sub(r'^https?://(?:dx\.)?doi.org/', '', value.strip().lower())
    if not re.fullmatch(r'10\.\d{4,9}/\S+', value) or 'example' in value: raise ValueError('Invalid/placeholder DOI')
    return value

class Paper(BaseModel):
    paper_id: str
    doi: str
    title: str
    authors: list[str]
    publication_year: int = Field(ge=1980, le=2100)
    journal_issn: list[str]
    verification_status: str = 'metadata_only'
    metadata_provenance: list[dict]
    model_config = {'extra':'allow'}
    @model_validator(mode='after')
    def valid(self):
        assert self.paper_id == 'doi:' + doi_key(self.doi)
        assert ISSNS.intersection(self.journal_issn)
        assert self.verification_status in STATUSES
        return self

class Variable(BaseModel):
    variable_id: str
    paper_id: str
    construct_en: str
    role: str
    verification_status: str = 'fulltext_screened'
    formula: str | None = None
    evidence_locator: str | None = None
    source_url: str | None = None
    source_hash: str | None = None
    extraction_method: str
    human_reviewer: str | None = None
    reviewed_at: str | None = None
    missingness: dict[str,str] = Field(default_factory=dict)
    model_config = {'extra':'allow'}
    @model_validator(mode='after')
    def supported(self):
        assert self.verification_status in STATUSES
        assert self.role in {'independent','dependent','mediator','moderator','control','instrument','selection','other','unknown'}
        if self.formula or self.verification_status in {'measurement_verified','human_reviewed'}:
            assert self.evidence_locator and self.source_url and self.source_hash, 'Primary source evidence required'
        if self.verification_status in {'measurement_verified','human_reviewed'}:
            assert self.extraction_method not in {'metadata','abstract','llm'}, 'Draft cannot verify measures'
        if self.verification_status == 'human_reviewed':
            assert self.human_reviewer and self.reviewed_at
        assert all(v in {'not_reported','not_verified','not_applicable'} for v in self.missingness.values())
        return self

def normalize(raw):
    if not ISSNS.intersection(raw.get('ISSN', [])): raise ValueError('Wrong journal ISSN')
    journal = ' '.join(raw.get('container-title', [])).lower()
    if journal != 'strategic management journal': raise ValueError('Journal title mismatch')
    doi = doi_key(raw['DOI'])
    def date(key):
        parts = raw.get(key, {}).get('date-parts', [[]])[0]
        return '-'.join(str(v).zfill(2) if i else str(v) for i,v in enumerate(parts)) or None
    pub = date('published-print') or date('published-online') or date('published')
    if not pub: raise ValueError('Missing publication year')
    record = dict(paper_id='doi:'+doi, doi=doi, title=' '.join(raw.get('title', [])), authors=[' '.join(filter(None,[a.get('given'),a.get('family')])) for a in raw.get('author',[])], publication_year=int(pub[:4]), online_date=date('published-online'), print_date=date('published-print'), journal_issn=sorted(set(raw['ISSN'])), volume=raw.get('volume'), issue=raw.get('issue'), pages=raw.get('page') or raw.get('article-number'), article_type=raw.get('type'), abstract=None, doi_url='https://doi.org/'+doi, publisher_url=raw.get('URL'), oa_url=None, openalex_id=None, citation_count=None, citation_count_asof=None, domain_codes=[], theory_tags=[], method_tags=[], industry_tags=[], geography_tags=[], verification_status='metadata_only', metadata_provenance=[{'source':'Crossref','source_url':'https://api.crossref.org/works/'+doi,'indexed':raw.get('indexed',{}).get('date-time')}], last_synced_at=now(), curation_updated_at=None)
    record.update(publication_year_basis='print' if date('published-print') else 'online' if date('published-online') else 'published',license_info=raw.get('license',[]),correction_relations=raw.get('relation',{}),update_notices=raw.get('update-to',[]),crossref_reference_count=raw.get('reference-count'))
    return Paper.model_validate(record).model_dump()

CURATED = {'domain_codes','theory_tags','method_tags','industry_tags','geography_tags','verification_status','curation_updated_at','summary','oa_url','legacy_domain_codes','legacy_theory_tags','taxonomy_version','taxonomy_tags','classifications'}
def upsert(old, new):
    if not old: return new
    merged = {**new, **{k:v for k,v in old.items() if k in CURATED}}
    comparable = lambda d: {k:v for k,v in d.items() if k != 'last_synced_at'}
    return old if comparable(old) == comparable(merged) else merged
