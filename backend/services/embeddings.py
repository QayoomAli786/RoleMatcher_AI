"""Embedding generation with caching. TF-IDF based (swappable for real embeddings)."""

from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)

# ── Tokeniser ─────────────────────────────────────────────────────────────────

import re

_WORD_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


# ── TF-IDF Vectoriser ────────────────────────────────────────────────────────


class TFIDFVectorizer:
    """Minimal TF-IDF vectoriser that works without sklearn."""

    def __init__(self, max_features: int = 5000, ngram_range: tuple[int, int] = (1, 1)) -> None:
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None
        self._fitted = False

    def _build_ngrams(self, tokens: list[str]) -> list[str]:
        grams: list[str] = []
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(tokens) - n + 1):
                grams.append(" ".join(tokens[i : i + n]))
        return grams

    def fit(self, documents: Sequence[str]) -> TFIDFVectorizer:
        doc_freq: Counter[str] = Counter()
        total = len(documents)
        for doc in documents:
            tokens = self._build_ngrams(_tokenize(doc))
            unique = set(tokens)
            doc_freq.update(unique)

        # Keep top features by document frequency
        sorted_terms = sorted(doc_freq.items(), key=lambda x: -x[1])[: self.max_features]
        self.vocab = {term: idx for idx, (term, _) in enumerate(sorted_terms)}

        self.idf = np.zeros(len(self.vocab))
        for term, idx in self.vocab.items():
            df = doc_freq.get(term, 0)
            self.idf[idx] = math.log((1 + total) / (1 + df)) + 1

        self._fitted = True
        return self

    def transform(self, documents: Sequence[str]) -> np.ndarray:
        if not self._fitted or self.idf is None:
            raise RuntimeError("Call fit() before transform()")
        rows = []
        for doc in documents:
            tokens = self._build_ngrams(_tokenize(doc))
            tf = Counter(tokens)
            vec = np.zeros(len(self.vocab))
            for term, count in tf.items():
                if term in self.vocab:
                    vec[self.vocab[term]] = count * self.idf[self.vocab[term]]
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            rows.append(vec)
        return np.array(rows)

    def fit_transform(self, documents: Sequence[str]) -> np.ndarray:
        self.fit(documents)
        return self.transform(documents)


# ── Embedding Cache ───────────────────────────────────────────────────────────


class EmbeddingCache:
    """Content-hash based embedding cache."""

    def __init__(self, backend: "EmbeddingService | None" = None) -> None:
        self._store: dict[str, np.ndarray] = {}
        self._backend = backend

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> np.ndarray | None:
        return self._store.get(self._hash(text))

    def set(self, text: str, vec: np.ndarray) -> None:
        self._store[self._hash(text)] = vec

    def contains(self, text: str) -> bool:
        return self._hash(text) in self._store


# ── Public API ────────────────────────────────────────────────────────────────


class EmbeddingService:
    """Deterministic embedding service using TF-IDF with content-hash caching."""

    def __init__(self, max_features: int = 5000) -> None:
        self._vectorizer = TFIDFVectorizer(max_features=max_features)
        self._cache = EmbeddingCache()
        self._fitted = False
        self._corpus: list[str] = []

    def fit(self, corpus: Sequence[str]) -> None:
        """Fit the vectorizer on a corpus of documents."""
        self._vectorizer.fit(list(corpus))
        self._corpus = list(corpus)
        self._fitted = True
        self._cache = EmbeddingCache()

    def ensure_fit(self, texts: Sequence[str]) -> None:
        """Fit if not already fitted."""
        if not self._fitted:
            self.fit(texts)

    def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding for a single text string. Returns list[float]."""
        cached = self._cache.get(text)
        if cached is not None:
            return cached.tolist()

        self.ensure_fit([text])
        vec = self._vectorizer.transform([text])[0]
        self._cache.set(text, vec)
        return vec.tolist()

    def compute_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Cosine similarity between two vectors."""
        a = np.array(vec1)
        b = np.array(vec2)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def batch_embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Batch-embed a list of texts."""
        results: list[list[float]] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, t in enumerate(texts):
            cached = self._cache.get(t)
            if cached is not None:
                results.append(cached.tolist())
            else:
                results.append([])
                uncached_indices.append(i)
                uncached_texts.append(t)

        if uncached_texts:
            self.ensure_fit(uncached_texts)
            new_vecs = self._vectorizer.transform(uncached_texts)
            for idx, vec in zip(uncached_indices, new_vecs):
                self._cache.set(texts[idx], vec)
                results[idx] = vec.tolist()

        return results


# ── Module-level singleton ────────────────────────────────────────────────────

_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service


def generate_embedding(text: str) -> list[float]:
    """Convenience function."""
    return get_embedding_service().generate_embedding(text)


def compute_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Convenience function."""
    return get_embedding_service().compute_similarity(vec1, vec2)


def batch_embed(texts: Sequence[str]) -> list[list[float]]:
    """Convenience function."""
    return get_embedding_service().batch_embed(texts)
