"""Source-aligned Theory detection in lawfully available SMJ full texts.

Named Theory mention != author-declared theoretical lens != verified application.
Only Introduction, Theory, Hypothesis and Conceptual sections are eligible.
No references, appendices, tables, or copyrighted source document republishing.
"""
import re

from .study import sentences
from .taxonomy import text_key
from .semantic import hits_for_text

THEORY_EXTRACTOR_VERSION="fulltext-theory-v1"
MAX_EVIDENCE_PER_TERM=3
SCOPE=re.compile(
    r"(?:\bintroduction\b|\btheor(?:y|ies|etical)\b|"
    r"\bhypothes(?:is|es)\b|\bpropositions?\b|"
    r"\bliterature\s+review\b|\bconceptual\s+(?:framework|development)\b)",
    re.I)
OUT_OF_SCOPE=re.compile(
    r"\b(?:references|bibliography|acknowledg(?:e)?ments?|"
    r"appendix|appendices|supplementary|supporting\s+information|"
    r"results?|discussion|conclusions?|methods?|measurement|data\s+and\s+methods)\b",
    re.I)
AUTHOR_USE=re.compile(
    r"(?:\bwe\s+(?:(?:explicitly|further|also|primarily|directly)\s+)?"
    r"(?:draw\s+on|draw\s+upon|build\s+on|build\s+upon|rely\s+on|"
    r"apply|adopt|use|employ|invoke|extend|integrate|ground\s+(?:our\s+)?"
    r"(?:hypotheses|analysis|framework)\s+in|develop\s+(?:our\s+)?"
    r"(?:framework|hypotheses)\s+(?:from|using|based\s+on))"
    r"|\bour\s+(?:(?:theoretical|conceptual)\s+)?"
    r"(?:framework|hypotheses|model|analysis)\s+"
    r"(?:draws?\s+on|builds?\s+on|is\s+grounded\s+in|is\s+based\s+on))",
    re.I)
NEGATED=re.compile(
    r"(?:\b(?:we\s+)?(?:do|does|did|are|is|was|were)\s+not\b|"
    r"\bwithout\b|\brather\s+than\b|\binstead\s+of\b|"
    r"\b(?:reject|rejected|rejecting)\b|\bnot\s+based\s+on\b)",
    re.I)


def _phrase_pattern(phrase):
    tokens=text_key(phrase).split()
    if len(tokens)<2 or len(tokens)>12:return None
    return re.compile(r"(?<![A-Za-z0-9])"+r"[\W_]+".join(map(re.escape,tokens))+
                      r"(?![A-Za-z0-9])",re.I)


def _section_allowed(section):
    section=(section or "").lower()
    if not section or section=="unknown":return False
    if OUT_OF_SCOPE.search(section):return False
    return bool(SCOPE.search(section))


def _declaration_before(sentence,offset):
    prefix=sentence[:offset]
    if not prefix:return False
    last=None
    for m in AUTHOR_USE.finditer(prefix):last=m
    if last is None or offset-last.end()>135:return False
    after_cue=prefix[last.start():]
    if NEGATED.search(after_cue):return False
    return True


def extract_theories(doc,taxonomy,registry,hypotheses=()):
    """Return source-span-aligned mentions, plus independently bounded scope.

    Status author_declared_use: a narrow first-person author statement.
    Status mentioned_in_section: a named theory occurred, but authorship
    or actual use is NOT inferred.
    Status context_candidate: only a weak related-lens multiword cue occurred.
    Author use is not peer-reviewed.
    """
    theory_nodes=[n for n in taxonomy.get("nodes",[]) if n.get("level")=="theory"
                  and not n["id"].startswith("OTHER-")]
    compiled={}
    for node in theory_nodes:
        patterns=[p for x in [node.get("label_en"),*node.get("match_phrases",[])]
                  if x for p in [_phrase_pattern(x)] if p is not None]
        if patterns:compiled[node["id"]]=patterns
    scoped=[b for b in doc.blocks if b.get("kind")=="paragraph"
            and _section_allowed(b.get("section"))]
    result={}
    hypothesis_blocks={}
    for h in hypotheses:
        for evid in h.get("evidence_ids",[]):
            row=registry.rows.get(evid)
            if row:hypothesis_blocks.setdefault(row["block_id"],set()).add(h["hypothesis_id"])
    for block in scoped:
        raw=block["text"]
        if len(raw)>20000:continue
        for sent_start,sent_end,_ in sentences(raw):
            # Raw offsets must be used for source-hash alignment even when
            # the sentence splitter strips leading whitespace.
            sent=raw[sent_start:sent_end]
            if len(sent)>1200:continue
            for term,patterns in compiled.items():
                matched=next((m for pat in patterns if (m:=pat.search(sent))),None)
                if not matched:continue
                start=sent_start+matched.start()
                end=sent_start+matched.end()
                declared=_declaration_before(sent,matched.start())
                ev=registry.add(block,max(sent_start,start-115),min(sent_end,end+45),
                    "fulltext_theory_author_declaration" if declared else "fulltext_theory_section_mention")
                entry=result.setdefault(term,dict(
                    term_id=term,status="mentioned_in_section",evidence_ids=[],
                    source_url=doc.source_url,source_hash=doc.source_hash,
                    section=block["section"],page=block.get("page"),
                    matched_phrase=sent[matched.start():matched.end()],
                    hypothesis_ids=[],validation_status="source_span_aligned_not_semantic_certification",
                    algorithm_version=THEORY_EXTRACTOR_VERSION))
                if declared:
                    entry.update(status="author_declared_use",section=block["section"],
                        page=block.get("page"),matched_phrase=sent[matched.start():matched.end()])
                if ev not in entry["evidence_ids"] and len(entry["evidence_ids"])<MAX_EVIDENCE_PER_TERM:
                    entry["evidence_ids"].append(ev)
                if declared:
                    entry["hypothesis_ids"]=sorted(set(entry["hypothesis_ids"])|
                        hypothesis_blocks.get(block["block_id"],set()))
    # Light, local contextual-retrieval layer: multiword theory lens
    # associations are candidates ONLY, not an embedding model or proof that
    # the author drew on a theory. Always subordinate to named phrase evidence.
    for block in scoped:
        if len(block["text"])>20000:continue
        for cue in hits_for_text(block["text"],taxonomy):
            if cue["dimension"]!="theory" or cue["term_id"] in result:continue
            phrase=cue["trigger"]
            normalized=text_key(block["text"])
            if text_key(phrase) not in normalized:continue
            # Locators need a byte-accurate source span; require the trigger
            # phrase to be literally present before creating an E2 record.
            pat=_phrase_pattern(phrase)
            match=pat.search(block["text"]) if pat else None
            if not match:continue
            start=max(0,match.start()-40);end=min(len(block["text"]),match.end()+45)
            ev=registry.add(block,start,end,"fulltext_contextual_theory_candidate")
            result[cue["term_id"]]=dict(
                term_id=cue["term_id"],status="context_candidate",
                evidence_ids=[ev],source_url=doc.source_url,source_hash=doc.source_hash,
                section=block["section"],page=block.get("page"),
                matched_phrase=block["text"][match.start():match.end()],
                hypothesis_ids=[],validation_status="candidate_not_verified",
                algorithm_version=THEORY_EXTRACTOR_VERSION)
    return (list(sorted(result.values(),key=lambda x:x["term_id"])),
            dict(status="scanned" if scoped else "no_identifiable_theory_sections",
                 scoped_blocks=len(scoped),scoped_sections=sorted({b["section"] for b in scoped}),
                 phrases_indexed=len(compiled),author_use_rule="local_first_person_cue_only",
                 limitations=["Mention does not prove adoption",
                              "Author-declared lens is not independently validated",
                              "No fulltext access or missing section cannot be treated as no theory"]))
