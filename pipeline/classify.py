"""Interpretable progressive multi-label classification; scores are not probabilities."""
import hashlib
import math
from collections import Counter
from .taxonomy import Assignment, text_key
from .core import now

def cosine(left,right):
    a=Counter(text_key(left).split());b=Counter(text_key(right).split())
    stop={'the','of','and','in','a','to','for','on','as','by','with','we','our','firm','firms','strategy','strategic'}
    for w in stop:a.pop(w,None);b.pop(w,None)
    norm=math.sqrt(sum(v*v for v in a.values())*sum(v*v for v in b.values()))
    return sum(v*b[k] for k,v in a.items())/norm if norm else 0

def classify(papers,taxonomy,enrichment=(),decisions=()):
    """Exact phrases -> lexical vector similarity -> optional separately configured provider."""
    enrichment={r['paper_id']:r for r in enrichment};manual={(a['paper_id'],a['term_id']) for a in decisions}
    nodes={n['id']:n for n in taxonomy['nodes']};output=list(decisions)
    for paper in papers:
        title=' '+text_key(paper['title'])+' ';extra=enrichment.get(paper['paper_id'],{})
        hits={}
        for node in nodes.values():
            if node['level'] not in {'research_topic','theory'}:continue
            title_match=any(' '+text_key(x)+' ' in title for x in node.get('match_phrases',[]))
            abstract_match=node['id'] in extra.get('abstract_phrase_hits',[])
            similarity=cosine(paper['title'],node['label_en']+' '+' '.join(node.get('match_phrases',[])))
            if title_match or abstract_match:hits[node['id']]=(1.0 if abstract_match else .8,'validated_automatic','E1_abstract' if abstract_match else 'E0_metadata','allowed_phrase_occurrence_v3')
            elif node['level']=='research_topic' and similarity>=.35:hits[node['id']]=(round(similarity,4),'provisional','E0_metadata','lexical_vector_cosine_v3')
        for ident,axes in list(hits.items()):
            for parent in nodes[ident]['parent_ids']:
                if parent not in hits or hits[parent][0]<axes[0]:hits[parent]=(*axes[:3],axes[3]+'+taxonomy_parent')
        for ident,(score,status,grade,method) in sorted(hits.items()):
            if (paper['paper_id'],ident) in manual:continue
            source=extra.get('source_url') if grade=='E1_abstract' else paper['metadata_provenance'][0]['source_url']
            digest=extra.get('abstract_hash') if grade=='E1_abstract' else hashlib.sha256(paper['title'].encode()).hexdigest()
            record=Assignment(assignment_id='auto:'+hashlib.sha256((paper['paper_id']+'|'+ident+'|v3').encode()).hexdigest()[:20],paper_id=paper['paper_id'],term_id=ident,taxonomy_version=taxonomy['version'],origin='algorithmic',method=method,source_url=source,evidence_locator='OpenAlex abstract phrase index' if grade=='E1_abstract' else 'Crossref title',input_hash=digest,review_status='suggested').model_dump()
            record.update(inference_origin='deterministic_rule',input_origin='openalex_metadata' if grade=='E1_abstract' else 'crossref_metadata',evidence_grade=grade,validation_status=status,heuristic_score=score,confidence_score=None,source_hash=digest,algorithm_version='atlas-classifier-3.0',retrieved_at=extra.get('retrieved_at') if grade=='E1_abstract' else paper['last_synced_at'],validation_scope='Source/label consistency only; not expert peer review',input_evidence_snippet=paper['title'] if grade=='E0_metadata' else None)
            output.append(record)
    return output
