"""Interpretable progressive multi-label classification; scores are not probabilities."""
import hashlib
import math
from collections import Counter
from .taxonomy import Assignment, text_key
from .semantic import title_hits,FEATURE_VERSION
from .core import now

def cosine(left,right):
    a=Counter(text_key(left).split());b=Counter(text_key(right).split())
    stop={'the','of','and','in','a','to','for','on','as','by','with','we','our','firm','firms','strategy','strategic'}
    for w in stop:a.pop(w,None);b.pop(w,None)
    norm=math.sqrt(sum(v*v for v in a.values())*sum(v*v for v in b.values()))
    return sum(v*b[k] for k,v in a.items())/norm if norm else 0

OTHER_BY_LEVEL={"domain":"OTHER-DOM","research_topic":"OTHER-TOP",
                "construct":"OTHER-CON","theory":"OTHER-TH"}
CLASSIFIER_VERSION="atlas-classifier-6.0-fulltext-theory"

def classify(papers,taxonomy,enrichment=(),decisions=(),researches=()):
    """Assign source-supported topic/construct/theory labels and an explicit
    insufficient-evidence Other fallback for each missing dimension.

    Unknowns are presentation categories, not claims about what the paper lacks.
    A domain is inferred from the explicitly mapped parents of matched topic
    or construct, never directly from an unlabeled theory.
    """
    enrichment={r['paper_id']:r for r in enrichment}
    research_by_paper={r['paper_id']:r for r in researches}
    manual={(a['paper_id'],a['term_id']) for a in decisions}
    rejected={(a['paper_id'],a['term_id']) for a in decisions if a['review_status']=='rejected'}
    nodes={n['id']:n for n in taxonomy['nodes']}
    output=list(decisions)
    levels=("domain","research_topic","construct","theory")
    for paper in papers:
        pid=paper['paper_id']
        title=" "+text_key(paper['title'])+" "
        extra=enrichment.get(pid,{})
        research=research_by_paper.get(pid,{})
        evidence_ids={e['evidence_id'] for e in research.get('evidence',[])}
        author_declarations={}
        section_mentions={}
        for evidence in research.get('theory_evidence',[]):
            term_id=evidence.get('term_id')
            if (term_id not in nodes or nodes[term_id]['level']!='theory'
                    or (pid,term_id) in manual or (pid,term_id) in rejected
                    or not evidence.get('evidence_ids')
                    or not set(evidence['evidence_ids'])<=evidence_ids
                    or evidence.get('source_hash')!=research.get('source_hash')):
                continue
            if evidence.get('status')=='author_declared_use':
                author_declarations[term_id]=evidence
            elif evidence.get('status') in {'mentioned_in_section','context_candidate'}:
                section_mentions[term_id]=evidence
        hits={}
        for node in nodes.values():
            if node['level'] not in {'research_topic','construct','theory'} or node['id'] in OTHER_BY_LEVEL.values() or (pid,node['id']) in rejected:
                continue
            phrases=[text_key(x) for x in node.get('match_phrases',[]) if text_key(x)]
            title_match=any(" "+x+" " in title for x in phrases)
            abstract_match=(node['id'] in extra.get('abstract_phrase_hits',[]) and
                            bool(extra.get('abstract_hash')))
            similarity=cosine(paper['title'],node['label_en']+' '+' '.join(node.get('match_phrases',[]))) if node['level']=='research_topic' else 0
            if abstract_match:
                hits[node['id']]=(1.0,'validated_automatic','E1_abstract','openalex_abstract_phrase_v5')
            elif title_match:
                hits[node['id']]=(.82,'validated_automatic','E0_metadata','crossref_title_exact_phrase_v5')
            elif node['level']=='research_topic' and similarity>=.35:
                hits[node['id']]=(round(similarity,4),'provisional','E0_metadata','title_similarity_cosine_v5')
        # A source-located, author-declared theory use outranks a title or
        # abstract phrase. A mere occurrence in a Theory section never does.
        for term_id in author_declarations:
            hits[term_id]=(1.0,'validated_automatic','E2_fulltext_section',
                           'source_aligned_author_declared_use_v1')

        # Separately retain weak contextual candidates; never present them as
        # theory adoption, verified constructs or a guaranteed literature label.
        # Unlike lexical labels, these do not propagate to ancestors or replace
        # the explicit Other fallback. A candidate is always opt-in in the UI.
        weak={}
        for item in title_hits(paper['title'],taxonomy):
            term_id=item['term_id']
            if term_id in nodes and term_id not in hits and (pid,term_id) not in manual:
                weak[term_id]=item
        if extra.get('abstract_hash'):
            for item in extra.get('abstract_weak_hits',[]):
                term_id=item.get('term_id')
                if (term_id in nodes and term_id not in hits and (pid,term_id) not in manual
                        and item.get('dimension')==nodes[term_id]['level']):
                    weak[term_id]=item
        for term_id,evidence in section_mentions.items():
            if term_id not in hits and (pid,term_id) not in manual:
                weak[term_id]=dict(term_id=term_id,dimension='theory',
                    trigger=evidence.get('matched_phrase'),
                    source='fulltext_mention',
                    method='source_aligned_theory_mention_not_author_use_v1',
                    heuristic_score=.55,evidence_ids=evidence['evidence_ids'],
                    section=evidence.get('section'),page=evidence.get('page'))
        for ident,item in sorted(weak.items()):
            fulltext_evidence=item.get('source')=='fulltext_mention'
            abstract_evidence=item.get('source')=='abstract_context' and bool(extra.get('abstract_hash'))
            source=(research['source_url'] if fulltext_evidence else
                extra.get('source_url') if abstract_evidence else paper['metadata_provenance'][0]['source_url'])
            source_hash=(research['source_hash'] if fulltext_evidence else
                extra['abstract_hash'] if abstract_evidence else hashlib.sha256(paper['title'].encode()).hexdigest())
            record=Assignment(
                assignment_id='candidate:'+hashlib.sha256((pid+'|'+ident+'|v5').encode()).hexdigest()[:20],
                paper_id=pid,term_id=ident,taxonomy_version=taxonomy['version'],
                origin='algorithmic',method=item.get('method',FEATURE_VERSION),
                source_url=source,evidence_locator=(
                    'Fulltext theory mention in '+str(item.get('section'))+' page '+str(item.get('page'))
                    if fulltext_evidence else
                    'Abstract weak lexical co-occurrence feature' if abstract_evidence
                    else 'Crossref title contextual phrase'),
                input_hash=source_hash,review_status='suggested').model_dump()
            record.update(is_fallback_other=False,is_semantic_candidate=True,
                inference_origin='fulltext_extraction' if fulltext_evidence else 'deterministic_rule',
                input_origin='fulltext_source' if fulltext_evidence else 'openalex_abstract_feature' if abstract_evidence else 'crossref_title',
                evidence_grade='E2_fulltext_section' if fulltext_evidence else 'E1_abstract' if abstract_evidence else 'E0_metadata',
                validation_status='semantic_candidate',
                heuristic_score=item.get('heuristic_score'),confidence_score=None,
                source_hash=source_hash,algorithm_version=CLASSIFIER_VERSION,
                retrieved_at=extra.get('retrieved_at') if abstract_evidence else paper.get('last_synced_at'),
                weak_trigger=item.get('trigger'),
                fulltext_evidence_ids=item.get('evidence_ids',[]) if fulltext_evidence else [],
                validation_scope='Candidate contextual co-occurrence only; no claim of adopted theory or measured construct')
            output.append(record)

        # L3 -> L2 -> L1. A construct may be mentioned even when a topic
        # phrase is absent. Mapping to ancestors is an editorial hierarchy,
        # not a claim that the authors used all those academic terms.
        pending=list(hits)
        while pending:
            ident=pending.pop()
            for parent in nodes[ident]['parent_ids']:
                if parent not in nodes or (pid,parent) in rejected:continue
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
                    origin='algorithmic',method='unresolved_no_supported_label_v5',
                    source_url=source,
                    evidence_locator="No supported category match in available title/abstract feature index",
                    input_hash=digest,review_status='suggested').model_dump()
                record.update(is_fallback_other=True,inference_origin='deterministic_rule',
                    evidence_grade='E0_metadata',
                    validation_status='insufficient_evidence',heuristic_score=None,
                    confidence_score=None,source_hash=digest,
                    algorithm_version=CLASSIFIER_VERSION,
                    retrieved_at=extra.get('retrieved_at') or paper.get('last_synced_at'),
                    validation_scope="No identified label; not proof of academic non-membership")
                output.append(record)

        for ident,(score,status,grade,method) in sorted(hits.items()):
            if (pid,ident) in manual:continue
            if grade=='E2_fulltext_section':
                source=research['source_url']
                digest=research['source_hash']
            elif grade=='E1_abstract':
                source=extra['source_url']
                digest=extra['abstract_hash']
            else:
                source=paper['metadata_provenance'][0]['source_url']
                digest=hashlib.sha256(paper['title'].encode()).hexdigest()
            record=Assignment(
                assignment_id='auto:'+hashlib.sha256((pid+'|'+ident+'|v5').encode()).hexdigest()[:20],
                paper_id=pid,term_id=ident,taxonomy_version=taxonomy['version'],
                origin='algorithmic',method=method,source_url=source,
                evidence_locator=(
                    'Author-declared theoretical lens in section '+str(author_declarations[ident].get('section'))+
                    ', page '+str(author_declarations[ident].get('page')) if grade=='E2_fulltext_section'
                    else 'OpenAlex abstract phrase features (not full abstract)'
                    if grade=='E1_abstract' else 'Crossref title and Atlas mapping'),
                input_hash=digest,review_status='suggested').model_dump()
            record.update(is_fallback_other=False,
                inference_origin='fulltext_extraction' if grade=='E2_fulltext_section' else 'deterministic_rule',
                input_origin='fulltext_source' if grade=='E2_fulltext_section' else 'openalex_metadata' if grade=='E1_abstract' else 'crossref_metadata',
                evidence_grade=grade,validation_status=status,heuristic_score=score,
                confidence_score=None,source_hash=digest,
                algorithm_version=CLASSIFIER_VERSION,
                retrieved_at=extra.get('retrieved_at') if grade=='E1_abstract' else paper.get('last_synced_at'),
                validation_scope='Rule and text-feature consistency; not peer-reviewed accuracy',
                input_evidence_snippet=paper['title'] if grade=='E0_metadata' else None,
                fulltext_evidence_ids=author_declarations[ident]['evidence_ids'] if grade=='E2_fulltext_section' else [],
                author_declared_use=grade=='E2_fulltext_section')
            output.append(record)
    return output
