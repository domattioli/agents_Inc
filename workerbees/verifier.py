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
        if _norm(c.get("quote", "")) and _norm(c["quote"]) in _norm(paras[int(m["n"]) - 1]):
            rep.matched += 1
        else:
            rep.failures.append({"claim": i, "reason": "quote_not_in_anchor", "anchor": c["anchor"]})
    return rep

def passed(report: Report) -> bool:
    return report.checked == report.matched
