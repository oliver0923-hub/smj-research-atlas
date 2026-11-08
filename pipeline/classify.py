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

OTHER_BY_LEVEL={"domain":"OTHER-DOM","research_topic":"OTHER-TOP",
                "construct":"OTHER-CON","theory":"OTHER-TH"}
CLASSIFIER_VERSION="atlas-classifier-4.0"

def classify(papers,taxonomy,enrichment=(),decisions=()):
    """Assign source-supported topic/construct/theory labels and an explicit
    insufficient-evidence Other fallback for each missing dimension.

    Unknowns are presentation categories, not claims about what the paper lacks.
    A domain is inferred from the explicitly mapped parents of matched topic
    or construct, never directly from an unlabeled theory.
    """
    enrichment={r['paper_id']:r for r in enrichment}
    manual={(a['paper_id'],a['term_id']) for a in decisions}
    nodes={n['id']:n for n in taxonomy['nodes']}
    output=list(decisions)
    levels=("domain","research_topic","construct","theory")
    for paper in papers:
        pid=paper['paper_id']
        title=" "+text_key(paper['title'])+" "
        extra=enrichment.get(pid,{})
        hits={}
        for node in nodes.values():
            if node['level'] not in {'research_topic','construct','theory'} or node['id'] in OTHER_BY_LEVEL.values():
                continue
            phrases=[text_key(x) for x in node.get('match_phrases',[]) if text_key(x)]
            title_match=any(" "+x+" " in title for x in phrases)
            abstract_match=(node['id'] in extra.get('abstract_phrase_hits',[]) and
                            bool(extra.get('abstract_hash')) and bool(extra.get('abstract_available')))
            similarity=cosine(paper['title'],node['label_en']+' '+' '.join(node.get('match_phrases',[]))) if node['level']=='research_topic' else 0
            if abstract_match:
                hits[node['id']]=(1.0,'validated_automatic','E1_abstract','openalex_abstract_phrase_v4')
            elif title_match:
                hits[node['id']]=(.82,'validated_automatic','E0_metadata','crossref_title_exact_phrase_v4')
            elif node['level']=='research_topic' and similarity>=.35:
                hits[node['id']]=(round(similarity,4),'provisional','E0_metadata','title_similarity_cosine_v4')
        # L3 -> L2 -> L1. A construct may be mentioned even when a topic
        # phrase is absent. Mapping to ancestors is an editorial hierarchy,
        # not a claim that the authors used all those academic terms.
        pending=list(hits)
        while pending:
            ident=pending.pop()
            for parent in nodes[ident]['parent_ids']:
                if parent not in nodes:continue
                if parent not in hits or hits[parent][0]<hits[ident][0]:
                    score,status,grade,method=hits[ident]
                    hits[parent]=(score,status,grade,method+"+atlas_hierarchy")
                    pending.append(parent)

        # Respect actual manual approvals/rejections without fabricating them.
        effective={n['level'] for a in decisions if a['paper_id']==pid and
                   a['review_status']=='approved' for n in [nodes.get(a['term_id'])] if n}
        effective.update(nodes[ident]['level'] for ident in hits if (pid,ident) not in manual)

        for level in levels:
            if level not in effective and OTHER_BY_LEVEL[level] in nodes and (pid,OTHER_BY_LEVEL[level]) not in manual:
                ident=OTHER_BY_LEVEL[level]
                key=pid+"|"+ident+"|"+taxonomy['version']
                source=paper['metadata_provenance'][0]['source_url']
                digest=hashlib.sha256((paper['title']+"|"+(extra.get('abstract_hash') or "")).encode()).hexdigest()
                record=Assignment(
                    assignment_id="other:"+hashlib.sha256(key.encode()).hexdigest()[:20],
                    paper_id=pid,term_id=ident,taxonomy_version=taxonomy['version'],
                    origin='algorithmic',method='unresolved_no_supported_label_v4',
                    source_url=source,
                    evidence_locator="No supported category match in available title/abstract feature index",
                    input_hash=digest,review_status='suggested').model_dump()
                record.update(is_fallback_other=True,inference_origin='deterministic_rule',
                    evidence_grade='E1_abstract' if extra.get('abstract_available') and extra.get('abstract_hash') else 'E0_metadata',
                    validation_status='insufficient_evidence',heuristic_score=None,
                    confidence_score=None,source_hash=digest,
                    algorithm_version=CLASSIFIER_VERSION,
                    retrieved_at=extra.get('retrieved_at') or paper.get('last_synced_at'),
                    validation_scope="No identified label; not proof of academic non-membership")
                output.append(record)

        for ident,(score,status,grade,method) in sorted(hits.items()):
            if (pid,ident) in manual:continue
            if grade=='E1_abstract':
                source=extra['source_url']
                digest=extra['abstract_hash']
            else:
                source=paper['metadata_provenance'][0]['source_url']
                digest=hashlib.sha256(paper['title'].encode()).hexdigest()
            record=Assignment(
                assignment_id='auto:'+hashlib.sha256((pid+'|'+ident+'|v4').encode()).hexdigest()[:20],
                paper_id=pid,term_id=ident,taxonomy_version=taxonomy['version'],
                origin='algorithmic',method=method,source_url=source,
                evidence_locator='OpenAlex abstract phrase features (not full abstract)'
                    if grade=='E1_abstract' else 'Crossref title and Atlas mapping',
                input_hash=digest,review_status='suggested').model_dump()
            record.update(is_fallback_other=False,
                inference_origin='deterministic_rule',
                input_origin='openalex_metadata' if grade=='E1_abstract' else 'crossref_metadata',
                evidence_grade=grade,validation_status=status,heuristic_score=score,
                confidence_score=None,source_hash=digest,
                algorithm_version=CLASSIFIER_VERSION,
                retrieved_at=extra.get('retrieved_at') if grade=='E1_abstract' else paper.get('last_synced_at'),
                validation_scope='Rule and text-feature consistency; not peer-reviewed accuracy',
                input_evidence_snippet=paper['title'] if grade=='E0_metadata' else None)
            output.append(record)
    return output
