import re
from collections import Counter

STOPWORDS = set("""a an the and or but if then else of to in on for with by from at as is are was were be been being it its this that these those
which who whom whose what when where why how i you he she we they me him her us them my your our their do does did done have has had having
not no yes so than too very can could should would will shall may might must about into over under again further once here there all any both
each few more most other some such only own same just also s t don now please tell show give find list what's whats get our""".split())

_word = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-']*")


def words(text: str) -> list[str]:
    return [w.lower() for w in _word.findall(text or "")]


def keywords(text: str) -> list[str]:
    return [w for w in words(text) if w not in STOPWORDS and len(w) > 1]


def stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{1,}", text or "")
    return [p.strip(" -•*\t") for p in parts if len(p.strip()) > 20]


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def overlap_score(query: str, text: str) -> float:
    q = {stem(w) for w in keywords(query)}
    if not q:
        return 0.0
    t = Counter(stem(w) for w in keywords(text))
    hits = sum(1 for w in q if t.get(w))
    return hits / len(q)


def truncate_tokens(text: str, max_tokens: int) -> str:
    limit = max_tokens * 4
    return text if len(text) <= limit else text[:limit] + "\n…[truncated]"
