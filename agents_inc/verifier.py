"""Deterministic checks. Never a model. Whitespace-normalized substring match inside the anchored paragraph."""
from __future__ import annotations
import hashlib, re
from dataclasses import dataclass, field

_ANCHOR = re.compile(r"^(?P<src>[^#]+)#p(?P<n>\d+)$")

@dataclass
class Report:
    checked: int
    matched: int
    failures: list[dict] = field(default_factory=list)
    source_hash: str = ""

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()

def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]

def verify(source_text: str, source_id: str, claims: list[dict]) -> Report:
    paras = paragraphs(source_text)
    rep = Report(checked=len(claims), matched=0,
                 source_hash=hashlib.sha256(source_text.encode()).hexdigest())
    for i, c in enumerate(claims):
        m = _ANCHOR.match(c.get("anchor", ""))
        if not m or m["src"] != source_id or not (1 <= int(m["n"]) <= len(paras)):
            rep.failures.append({"claim": i, "reason": "bad_anchor", "anchor": c.get("anchor")})
            continue
        quote_norm = _norm(c.get("quote", ""))
        if quote_norm:
            # Match with word boundaries: \b won't work in regex after _norm strips punctuation,
            # so use negative lookahead/lookbehind with \w
            pattern = r"(?<!\w)" + re.escape(quote_norm) + r"(?!\w)"
            if re.search(pattern, _norm(paras[int(m["n"]) - 1])):
                rep.matched += 1
            else:
                rep.failures.append({"claim": i, "reason": "quote_not_in_anchor", "anchor": c["anchor"]})
        else:
            rep.failures.append({"claim": i, "reason": "quote_not_in_anchor", "anchor": c["anchor"]})
    return rep

def passed(report: Report) -> bool:
    return report.checked > 0 and report.checked == report.matched

def check_draft(draft: str, anchored: set[str]) -> dict:
    """Check draft citations against anchored paragraph set.

    Args:
        draft: Draft text with citations like (p3)
        anchored: Set of paragraph numbers that have anchored claims

    Returns:
        Dict with: sentences (int), cited (int), uncited_sentences (list), bad_citations (list)
    """
    # Split sentences on .!? followed by space
    sentences = re.split(r"(?<=[.!?])\s+", draft.strip())
    sentences = [s for s in sentences if s.strip()]

    uncited = []
    bad_cites = set()
    cited_count = 0

    for sent in sentences:
        # Find all citations (pN) in this sentence
        cites = re.findall(r"\(p(\d+)\)", sent)
        if not cites:
            uncited.append(sent)
        else:
            cited_count += 1
            # Track bad citations
            for cite_n in cites:
                if cite_n not in anchored:
                    bad_cites.add(cite_n)

    return {
        "sentences": len(sentences),
        "cited": cited_count,
        "uncited_sentences": uncited,
        "bad_citations": sorted(bad_cites)
    }
