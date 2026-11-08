"""Versioned, source-attributed taxonomy and reversible classification proposals."""
import hashlib
import html
import re
from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from .evidence import Origin, Grade, Validation

ORIGINS = Literal['official_academic_organization', 'custom_research', 'algorithmic']


class Term(BaseModel):
    id: str
    level: Literal['domain', 'research_topic', 'construct', 'operational_variable', 'theory']
    label_zh: str
    label_en: str
    parent_ids: list[str]
    origin: ORIGINS
    source_ids: list[str] = Field(min_length=1)
    method: str = Field(min_length=1)
    version: str
    review_status: Literal['needs_review', 'approved', 'rejected']
    reviewer: str | None = None
    reviewed_at: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    description: str = ''
    official_label_en: str | None = None
    paper_id: str | None = None
    variable_id: str | None = None
    evidence_locator: str | None = None
    source_url: str | None = None
    inference_origin: Origin | None = None
    evidence_grade: Grade | None = None
    validation_status: Validation | None = None

    @model_validator(mode='after')
    def provenance(self):
        if self.level in {'domain', 'theory'} and self.parent_ids:
            raise ValueError('Domain and independent Theory dimension cannot have hierarchy parents')
        if self.origin == 'official_academic_organization' and (self.level != 'domain' or not self.official_label_en):
            raise ValueError('Official origin is reserved for externally sourced SMS IG labels, not Atlas mappings')
        if self.review_status == 'approved' and not (self.reviewer and self.reviewed_at):
            raise ValueError('Human approval requires reviewer and date')
        if self.level == 'operational_variable' and not all([self.paper_id, self.variable_id, self.evidence_locator, self.source_url]):
            raise ValueError('Operational Variable must identify a paper-specific measure and evidence')
        return self


class Assignment(BaseModel):
    assignment_id: str
    paper_id: str
    term_id: str
    taxonomy_version: str
    origin: ORIGINS
    method: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    evidence_locator: str = Field(min_length=1)
    input_hash: str = Field(min_length=1)
    review_status: Literal['suggested', 'approved', 'rejected'] = 'suggested'
    reviewer: str | None = None
    reviewed_at: str | None = None
    audit_log: list[dict] = Field(default_factory=list)
    inference_origin: Origin | None = None
    evidence_grade: Grade | None = None
    validation_status: Validation | None = None
    heuristic_score: float | None = Field(default=None,ge=0,le=1)
    algorithm_version: str | None = None
    source_hash: str | None = None

    @model_validator(mode='after')
    def human_gate(self):
        if not self.source_url.startswith(('https://', 'http://')):
            raise ValueError('Evidence URL must use HTTP(S)')
        if self.origin == 'official_academic_organization':
            raise ValueError('SMS IG membership does not provide official paper assignments')
        if self.review_status in {'approved', 'rejected'}:
            if not all([self.reviewer, self.reviewed_at, self.audit_log]):
                raise ValueError('A human decision requires reviewer, date, and audit event')
            event = self.audit_log[-1]
            if event.get('decision') != self.review_status or event.get('reviewer') != self.reviewer:
                raise ValueError('Review decision must match the latest audit event')
            if event.get('human_attestation') is not True:
                raise ValueError('Human review requires explicit attestation in the audit event')
        return self


def validate_taxonomy(taxonomy, assignments=(), papers=(), variables=()):
    if taxonomy.get('is_official_smj_taxonomy') is not False:
        raise ValueError('Atlas must not claim an official SMJ taxonomy')
    version = taxonomy['version']
    sources = {s['id'] for s in taxonomy['sources']}
    nodes = {}
    for raw in taxonomy['nodes']:
        term = Term.model_validate(raw)
        if term.id in nodes or term.version != version or not set(term.source_ids) <= sources:
            raise ValueError('Duplicate term, unknown source, or mismatched taxonomy version')
        nodes[term.id] = term
    expected = {'research_topic': 'domain', 'construct': 'research_topic', 'operational_variable': 'construct'}
    paper_ids = {p['paper_id'] for p in papers}
    measures = {v['variable_id']: v for v in variables}
    for term in nodes.values():
        if term.level in expected:
            if not term.parent_ids or any(p not in nodes or nodes[p].level != expected[term.level] for p in term.parent_ids):
                raise ValueError('Invalid four-level hierarchy edge')
        if term.level == 'operational_variable':
            measure = measures.get(term.variable_id)
            if not measure or measure['paper_id'] != term.paper_id or term.paper_id not in paper_ids:
                raise ValueError('Operational Variable must resolve to its actual paper measure')
    seen = set()
    seen_pairs = set()
    for raw in assignments:
        a = Assignment.model_validate(raw)
        if (a.assignment_id in seen or a.term_id not in nodes or a.paper_id not in paper_ids or
            (a.taxonomy_version != version and not (a.taxonomy_version in taxonomy.get('legacy_versions',[])
              and a.review_status in {'approved','rejected'}))):
            raise ValueError('Duplicate or dangling classification assignment')
        if (a.paper_id,a.term_id) in seen_pairs:
            raise ValueError('Conflicting duplicate classification for the same paper and term')
        seen.add(a.assignment_id)
        seen_pairs.add((a.paper_id,a.term_id))
    return nodes


def text_key(text):
    return ' '.join(re.findall(r'[a-z0-9]+', html.unescape(re.sub(r'<[^>]+>', ' ', text)).lower()))


def suggest_assignments(papers, taxonomy, reviewed=()):
    """Title phrases suggest tags; never imply primary-source construct/measure verification."""
    nodes = {n['id']: n for n in taxonomy['nodes']}
    decisions = {(a['paper_id'], a['term_id']) for a in reviewed}
    proposals = []
    for paper in papers:
        title = text_key(paper['title'])
        hits = set()
        for node in nodes.values():
            if node['level'] not in {'research_topic', 'theory'}:
                continue
            if any(' '+text_key(phrase)+' ' in ' '+title+' ' for phrase in node.get('match_phrases', [])):
                hits.add(node['id'])
        # Ancestors are suggestions too. Never infer a construct or formula from a topic.
        for node_id in list(hits):
            hits.update(nodes[node_id]['parent_ids'])
        for node_id in sorted(hits):
            if (paper['paper_id'], node_id) in decisions:
                continue
            key = paper['paper_id']+'|'+node_id+'|'+taxonomy['version']
            proposals.append(Assignment(
                assignment_id='suggestion:'+hashlib.sha256(key.encode()).hexdigest()[:20],
                paper_id=paper['paper_id'], term_id=node_id, taxonomy_version=taxonomy['version'],
                origin='algorithmic', method='title_phrase_and_domain_ancestor_v1',
                source_url=paper['metadata_provenance'][0]['source_url'],
                evidence_locator='Crossref title (keyword occurrence only)',
                input_hash=hashlib.sha256(paper['title'].encode()).hexdigest(),
            ).model_dump())
    return proposals


STOP = set('a an the of in on for and or to from with by at as is are be does do how when why what which who its their firms firm evidence study effects effect role impact strategic strategy management performance between through new'.split())


def emerging_topics(papers, taxonomy, limit=20):
    """Budgeted lexical discovery, not a claim of theoretical novelty or consensus."""
    if not papers:
        return []
    end = max(p['publication_year'] for p in papers)
    recent = Counter(); baseline = Counter(); examples = defaultdict(list)
    known = {text_key(x) for n in taxonomy['nodes'] for x in [n['label_en'], *n.get('synonyms', []), *n.get('match_phrases', [])]}
    recent_n = baseline_n = 0
    for paper in papers:
        year = paper['publication_year']
        if not end-9 <= year <= end:
            continue
        current = year >= end-4
        recent_n += current; baseline_n += not current
        words = text_key(paper['title']).split()
        phrases = {' '.join(words[i:i+2]) for i in range(len(words)-1) if all(len(w)>2 and w not in STOP for w in words[i:i+2])}
        for phrase in phrases-known:
            (recent if current else baseline)[phrase] += 1
            if current: examples[phrase].append(paper['paper_id'])
    result = []
    for phrase, count in recent.items():
        ratio = ((count+1)/(recent_n+2))/((baseline[phrase]+1)/(baseline_n+2))
        if count < 3 or ratio < 1.5:
            continue
        result.append(dict(candidate_id='emerging:'+hashlib.sha256((phrase+str(end)).encode()).hexdigest()[:16],
            label_en=phrase, proposed_level='research_topic', proposed_parent_ids=[], origin='algorithmic',
            method='title_bigram_document_frequency_v1', source_ids=['ATLAS-METHOD'],
            source_paper_ids=sorted(examples[phrase]), taxonomy_version=taxonomy['version'],
            recent_window=[end-4,end], baseline_window=[end-9,end-5], recent_documents=count,
            baseline_documents=baseline[phrase], recent_denominator=recent_n, baseline_denominator=baseline_n,
            smoothed_prevalence_ratio=round(ratio,4), review_status='suggested', reviewer=None,
            caution='詞彙成長候選，非已確認的新興研究領域；需人工檢查語意、樣本與時間偏誤。'))
    return sorted(result,key=lambda r:(-r['smoothed_prevalence_ratio'],-r['recent_documents'],r['label_en']))[:limit]


def enrich_papers(papers, taxonomy, assignments):
    nodes = {n['id']: n for n in taxonomy['nodes']}
    by_paper = defaultdict(list)
    for assignment in assignments:
        by_paper[assignment['paper_id']].append(assignment)
    output = []
    for paper in papers:
        result = dict(paper)
        result['legacy_domain_codes'] = paper.get('legacy_domain_codes',paper.get('domain_codes',[]))
        result['legacy_theory_tags'] = paper.get('legacy_theory_tags',paper.get('theory_tags',[]))
        result['taxonomy_version'] = taxonomy['version']
        result['classifications'] = by_paper[paper['paper_id']]
        result['taxonomy_tags'] = {status:{level:[] for level in ['domain','research_topic','construct','operational_variable','theory']} for status in ['approved','suggested']}
        result['taxonomy_tags'].update({status:{level:[] for level in ['domain','research_topic','construct','operational_variable','theory']} for status in ['automatic','provisional','active','unresolved']})
        for a in result['classifications']:
            if a['review_status'] in result['taxonomy_tags']:
                result['taxonomy_tags'][a['review_status']][nodes[a['term_id']]['level']].append(a['term_id'])
            level=nodes[a['term_id']]['level']
            if a.get('is_fallback_other') and a['review_status']!='rejected':
                result['taxonomy_tags']['unresolved'][level].append(a['term_id'])
            if a.get('validation_status') in {'validated_automatic','provisional'} and a['review_status']!='rejected':
                target='automatic' if a['validation_status']=='validated_automatic' else 'provisional'
                result['taxonomy_tags'][target][level].append(a['term_id'])
            if a['review_status']=='approved' or (a['review_status']!='rejected' and
                    (a.get('validation_status') in {'validated_automatic','provisional'} or a.get('is_fallback_other'))):
                result['taxonomy_tags']['active'][level].append(a['term_id'])
        result['domain_codes'] = sorted(set(result['taxonomy_tags']['active']['domain']))
        result['theory_tags'] = sorted(set(result['taxonomy_tags']['active']['theory']))
        quality={}
        for level in ('domain','research_topic','construct','theory'):
            active=[a for a in result['classifications'] if nodes[a['term_id']]['level']==level
                    and a['review_status']!='rejected']
            substantive=[a for a in active if not a.get('is_fallback_other')
                         and (a['review_status']=='approved' or a.get('validation_status') in {'validated_automatic','provisional'})]
            abstract=[a for a in substantive if a.get('evidence_grade')=='E1_abstract']
            exact=[a for a in substantive if a.get('validation_status')=='validated_automatic']
            best=abstract or exact or substantive
            quality[level]=dict(
                state=('abstract_supported' if abstract else
                       'title_supported' if exact else
                       'provisional' if substantive else 'unresolved_other'),
                substantive_terms=sorted({a['term_id'] for a in substantive}),
                is_unresolved=not bool(substantive),
                fallback_terms=sorted({a['term_id'] for a in active if a.get('is_fallback_other')}),
                best_evidence_grade='E1_abstract' if abstract else 'E0_metadata' if substantive else None,
                matching_rules=[a.get('method') for a in best],
                score=max((a.get('heuristic_score') or 0 for a in substantive),default=None),
                disclaimer='Uncalibrated automatic lexical tagging; no guarantee of paper-level semantic accuracy'
            )
        result['taxonomy_quality']=quality
        output.append(result)
    return output
