"""Conservative, source-aligned hypothesis, finding and robustness claims.

Extracts explicit prose statements only. It cannot infer p-values, effect signs,
hypothesis support, or evidence of a robust result from mere section headings.
"""
import hashlib
import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator

STUDY_VERSION="study-claims-v1"
KIND=Literal["hypothesis","proposition","finding","robustness","sensitivity"]
SUPPORT=Literal["supported","not_supported","partially_supported","mixed","unknown"]
SIGNIFICANCE=Literal["significant","not_significant","mixed","unknown"]
RESULT=Literal["holds","does_not_hold","mixed","unknown"]


class StudyClaim(BaseModel):
    claim_id: str
    paper_id: str
    claim_type: KIND
    label: str | None = None
    statement_excerpt: str
    hypothesis_label: str | None = None
    related_hypothesis_id: str | None = None
    support_status: SUPPORT = "unknown"
    significance: SIGNIFICANCE = "unknown"
    robustness_result: RESULT = "unknown"
    variables: list[str] = Field(default_factory=list)
    test_description: str | None = None
    source_url: str
    source_hash: str
    source_page: int | None = None
    source_span_start: int
    source_span_end: int
    span_hash: str
    evidence_locator: str
    evidence_excerpt: str
    validation_status: Literal["validated_automatic","provisional"] = "validated_automatic"
    evidence_grade: Literal["E2_fulltext_section"]="E2_fulltext_section"
    inference_origin: Literal["fulltext_extraction"]="fulltext_extraction"
    algorithm_version: str = STUDY_VERSION
    missing_reason: dict[str,str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_fields(self):
        if self.source_span_end <= self.source_span_start:
            raise ValueError("Invalid source span")
        if len(self.evidence_excerpt.split())>24 or not self.evidence_excerpt:
            raise ValueError("Evidence excerpt must be short")
        if self.claim_type in ("hypothesis","proposition") and self.support_status != "unknown":
            raise ValueError("Hypothesis statements are not result statements")
        if self.claim_type != "finding" and self.significance != "unknown":
            raise ValueError("Significance requires an explicit finding")
        if self.claim_type not in ("robustness","sensitivity") and self.robustness_result != "unknown":
            raise ValueError("Robustness status requires a corresponding test")
        if self.claim_type == "finding" and not self.hypothesis_label:
            raise ValueError("Finding must explicitly name a hypothesis")
        return self


LABEL=re.compile(r"\b(?:(Hypothes(?:is|es)|Proposition)\s*(\d+[a-z]?)|(?<![A-Za-z])(H|P)\s*(\d+[a-z]?))\b",re.I)
INTRO=re.compile(r"(?i)\b(?:hypothesis\s*\d+[a-z]?|proposition\s*\d+[a-z]?|H\s*\d+[a-z]?|P\s*\d+[a-z]?)\s*(?:[:.]\s*|[-–—]\s+)")
RESULT_WORDS=re.compile(r"\b(support(?:ed|s|ing)?|confirm(?:ed|s)?|fail(?:s|ed)?\s+to\s+support|not\s+supported|partial(?:ly)?|mixed|significan(?:t|ce)|non[- ]?significant|insignificant|p\s*[<=>])\b",re.I)
TEST_WORDS={
    "robustness":re.compile(r"\b(robustness(?:\s+checks?)?|robust\s+(?:to|across|when)|results?\s+(?:remain|are)\s+robust)\b",re.I),
    "sensitivity":re.compile(r"\b(sensitivity\s+analys(?:is|es)|sensitivity\s+checks?|sensitive\s+to)\b",re.I)
}


def normalized(text):
    return " ".join(text.split())


def sentences(text):
    """Return likely sentence spans without splitting p-values at decimals."""
    boundaries=[0]+[m.end() for m in re.finditer(r"[.!?]\s+(?=[A-Z])",text)]+[len(text)]
    for start,end in zip(boundaries,boundaries[1:]):
        segment=text[start:end]
        if len(segment.strip())>=25:
            yield start,end,segment.strip()


def tag(label):
    m=LABEL.search(label)
    if not m:return None
    prefix="H" if (m.group(1) or m.group(3) or "").lower().startswith("h") else "P"
    number=m.group(2) or m.group(4)
    return prefix+number.lower()


def finding_status(segment):
    """Conservative explicit support / significance cues, with negation priority.

    Unsupported != statistically insignificant; a p-value for a different
    coefficient should never be inferred as hypothesis-level significance.
    """
    s=segment.lower()
    partial=re.search(r"\b(partial(?:ly)?\s+support(?:ed)?|mixed\s+(?:support|evidence|results?))\b",s)
    negative=re.search(
        r"\b(?:not\s+supported|unsupported|"
        r"fail(?:ed|s)?\s+to\s+(?:find\s+)?support|"
        r"(?:do|does|did|can|could|would)\s+not\s+(?:find\s+)?(?:support|confirm)|"
        r"(?:no|lack(?:s|ed)?\s+of|little)\s+(?:statistical\s+)?support|"
        r"no\s+evidence\s+(?:in\s+)?support\s+of|"
        r"did\s+not\s+find\s+evidence\s+(?:in\s+)?support\s+of|"
        r"not\s+confirmed)\b",s)
    positive=re.search(r"\b(support(?:ed|s)?|confirm(?:ed|s)?)\b",s)
    if partial:
        support="partially_supported" if "partial" in partial.group(0) else "mixed"
    elif negative:
        support="not_supported"
    elif positive:
        support="supported"
    else:
        support="unknown"

    insignificant=re.search(
        r"\b(?:non[- ]?significant|insignificant|"
        r"not\s+(?:statistically\s+)?significant|"
        r"no\s+(?:statistically\s+)?significant\s+(?:effect|relationship|association|coefficient)|"
        r"lack\s+of\s+(?:statistical\s+)?significance|"
        r"fails?\s+to\s+(?:reach|achieve)\s+(?:statistical\s+)?significance)\b",s)
    significant=re.search(r"\b(?:statistically\s+)?significant\b",s)
    explicit_p=re.search(r"\bp\s*<\s*(?:0?\.05|0?\.01|0?\.001)\b",s)
    if insignificant:
        significance="not_significant"
    elif significant or explicit_p:
        significance="significant"
    else:
        significance="unknown"
    return support,significance


def robustness_status(segment):
    s=segment.lower()
    if re.search(r"\b(no\s+longer\s+(?:holds?|robust)|not\s+robust|fails?\s+to\s+hold)\b",s):
        return "does_not_hold"
    if re.search(r"\b(hold(?:s)?|remain(?:s|ed)?\s+(?:robust|consistent|significant)|robust\s+to)\b",s):
        return "holds"
    if re.search(r"\bmixed\s+results?\b",s):return "mixed"
    return "unknown"


def verify_claim(record,pages):
    page=next((p for p in pages if p["page"]==record["source_page"]),None)
    if not page:raise ValueError("Source page not found")
    text=normalized(page["text"])
    span=text[record["source_span_start"]:record["source_span_end"]]
    if hashlib.sha256(span.encode()).hexdigest()!=record["span_hash"]:
        raise ValueError("Claim source-span mismatch")
    if record["evidence_excerpt"]!=" ".join(span.split()[:20]):
        raise ValueError("Claim evidence-excerpt mismatch")
    StudyClaim.model_validate(record)
    return True


def extract_study_claims(paper,pages,receipt):
    """Only explicit labeled statements; never claim comprehensive extraction."""
    if not receipt.get("accessible"):return []
    found=[];seen=set();hypotheses={}
    for page in pages:
        text=normalized(page["text"])
        for start,end,sentence in sentences(text):
            labels=list(LABEL.finditer(sentence))
            unique_labels={tag(x.group(0)) for x in labels}
            # Multiple hypothesis labels in one sentence require relation
            # extraction, not one shared binary result.
            if len(unique_labels)>1:continue
            label=tag(labels[0].group(0)) if labels else None
            # Hypothesis/proposition declaration must start near beginning.
            intro=INTRO.search(sentence)
            kind=None;support="unknown";significance="unknown";robustness="unknown"
            if intro and intro.start()<20 and label:
                kind="hypothesis" if label.startswith("H") else "proposition"
            elif label and label.startswith("H") and RESULT_WORDS.search(sentence):
                kind="finding"
                support,significance=finding_status(sentence)
                if support=="unknown" and significance=="unknown":
                    kind=None
            else:
                for check,pattern in TEST_WORDS.items():
                    if pattern.search(sentence):
                        kind=check
                        robustness=robustness_status(sentence)
                        break
            if not kind:continue
            # Do not claim significance from a p-value without a labeled
            # hypothesis in the same sentence (especially tables).
            excerpt=" ".join(sentence.split()[:20])
            span=text[start:end];label_for_key=label or ""
            key="|".join([paper["paper_id"],kind,label_for_key,hashlib.sha256(span.encode()).hexdigest()])
            if key in seen:continue
            claim_id="claim:"+hashlib.sha256(key.encode()).hexdigest()[:24]
            record=StudyClaim(
                claim_id=claim_id,paper_id=paper["paper_id"],claim_type=kind,
                label=label if kind in ("hypothesis","proposition") else None,
                hypothesis_label=label if kind=="finding" else None,
                statement_excerpt=excerpt,
                support_status=support,significance=significance,robustness_result=robustness,
                source_url=receipt["source_url"],source_hash=receipt["source_hash"],
                source_page=page["page"],source_span_start=start,source_span_end=end,
                span_hash=hashlib.sha256(span.encode()).hexdigest(),
                evidence_locator=(("PDF page "+str(page["page"])) if page["page"] else "HTML paragraph")
                    +"; normalized characters "+str(start)+"–"+str(end),
                evidence_excerpt=" ".join(span.split()[:20]),
                missing_reason={
                    "variable_links":"not_grounded_by_structured_model_evidence",
                    "statistical_significance":"not_explicit" if significance=="unknown" else "explicit_sentence_only",
                    "model_or_table":"not_parsed"
                }
            ).model_dump()
            verify_claim(record,pages)
            if kind in ("hypothesis","proposition") and label:
                hypotheses.setdefault(label,claim_id)
            seen.add(key);found.append(record)
    # Link results to explicit hypothesis records in the same article.
    for record in found:
        if record["claim_type"]=="finding":
            record["related_hypothesis_id"]=hypotheses.get(record["hypothesis_label"])
    return found
