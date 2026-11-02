"""Embedding provider abstraction with explicit model versioning (chunks store the embedding_model they were built with)."""
import hashlib
import math
from app.ai.textutil import words, stem
from app.core.config import get_settings


class LocalHashEmbedder:
    """Deterministic feature-hashing embedder (unigrams + bigrams, signed hashing, log-tf, L2 norm).
    Captures lexical similarity only; used when no embedding API is configured and for reproducible tests."""
    model = "local-hash-v1"
    dim = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        toks = [stem(w) for w in words(text)]
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        counts: dict[str, int] = {}
        for f in feats:
            counts[f] = counts.get(f, 0) + 1
        for f, c in counts.items():
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            idx, sign = h % self.dim, (1.0 if (h >> 63) & 1 else -1.0)
            vec[idx] += sign * (1 + math.log(c)) * (0.5 if "_" in f else 1.0)
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAIEmbedder:
    model = "text-embedding-3-small"
    dim = 1536

    def __init__(self):
        import openai
        self.client = openai.OpenAI(api_key=get_settings().openai_api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i in range(0, len(texts), 96):
            resp = self.client.embeddings.create(model=self.model, input=[t[:8000] for t in texts[i:i + 96]])
            out.extend(d.embedding for d in resp.data)
        return out


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        s = get_settings()
        if s.embedding_provider == "openai" or (s.embedding_provider == "auto" and s.openai_api_key):
            _embedder = OpenAIEmbedder()
        else:
            _embedder = LocalHashEmbedder()
    return _embedder
