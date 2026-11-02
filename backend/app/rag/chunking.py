"""Configurable chunking strategies. See RAG_DESIGN.md for the evaluation that chose 'recursive' as default."""
import re
from dataclasses import dataclass
from app.ai.textutil import estimate_tokens, sentences
from app.rag.extraction import Section

STRATEGIES = {"recursive": {"target_tokens": 350, "overlap_tokens": 50}, "fixed": {"target_tokens": 300, "overlap_tokens": 0},
              "sentence": {"target_tokens": 200, "overlap_tokens": 0}}


@dataclass
class Chunk:
    content: str
    page: int | None
    section: str | None
    index: int = 0

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)


def _split_units(text: str, strategy: str) -> list[str]:
    if strategy == "fixed":
        size = STRATEGIES["fixed"]["target_tokens"] * 4
        return [text[i:i + size] for i in range(0, len(text), size)]
    if strategy == "sentence":
        return sentences(text) or [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units = []
    limit = STRATEGIES["recursive"]["target_tokens"]
    for p in paras:
        if estimate_tokens(p) <= limit:
            units.append(p)
        else:
            units.extend(sentences(p) or [p])
    return units


def chunk_sections(sections: list[Section], strategy: str = "recursive") -> list[Chunk]:
    cfg = STRATEGIES.get(strategy, STRATEGIES["recursive"])
    target, overlap = cfg["target_tokens"], cfg["overlap_tokens"]
    chunks: list[Chunk] = []
    for sec in sections:
        units = _split_units(sec.text, strategy)
        buf: list[str] = []
        for u in units:
            if buf and estimate_tokens(" ".join(buf + [u])) > target:
                chunks.append(Chunk(content="\n".join(buf), page=sec.page, section=sec.heading))
                if overlap:
                    tail, acc = [], 0
                    for prev in reversed(buf):
                        acc += estimate_tokens(prev)
                        tail.insert(0, prev)
                        if acc >= overlap:
                            break
                    buf = tail if acc < target else []
                else:
                    buf = []
            buf.append(u)
        if buf:
            chunks.append(Chunk(content="\n".join(buf), page=sec.page, section=sec.heading))
    for i, c in enumerate(chunks):
        c.index = i
    return [c for c in chunks if c.content.strip()]
