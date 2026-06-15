"""
Phase-2 retrieval: pick candidate tables by VECTOR SIMILARITY instead of
hand-written synonym regexes — this is what lets the system scale to hundreds
of tables.

Why this matters: Phase 1 picked a table with `re.search` over a synonym list.
That works for a handful of tables but doesn't scale to 500 — you can't
hand-author every phrasing. Here we instead build one "document" per table
(its description + synonyms + column names/descriptions), embed all of them,
embed the question, and rank tables by cosine similarity. Only the top-ranked
table(s) flow downstream.

This POC uses a lightweight, fully-offline TF-IDF embedder (deterministic, no
API key, no model download) so the whole pipeline stays runnable. The embedder
is the ONLY thing you swap for production: drop in a real semantic embedding
model — Voyage AI (Anthropic's recommended embedding provider) or a local
sentence-transformers model — and store the vectors in a vector DB (pgvector,
Qdrant, Chroma). The ranking logic is identical; real embeddings just generalize
better to phrasings the synonyms never listed.
"""

import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

_WORD = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """
    Lowercase, split into words, drop English stop-words, and crudely
    singularize (issues->issue, changes->change). The singularization is what a
    lexical embedder needs to match plural questions to singular synonyms; a
    real semantic embedding model would handle this (and far more) on its own.
    """
    out = []
    for tok in _WORD.findall(text.lower()):
        if len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]
        if tok not in ENGLISH_STOP_WORDS:
            out.append(tok)
    return out


def _table_document(table: str, meta: dict) -> str:
    """The text that represents a table for retrieval — what we embed."""
    parts = [table, meta.get("description", "")]
    parts += meta.get("synonyms", [])
    for col, info in meta.get("columns", {}).items():
        parts.append(col)
        parts.append(info.get("description", ""))
    return " ".join(parts)


class TableRetriever:
    """Ranks tables by similarity to a natural-language question."""

    def __init__(self, layer: dict):
        self.tables = list(layer["tables"])
        docs = [_table_document(t, layer["tables"][t]) for t in self.tables]
        # TfidfVectorizer L2-normalizes rows, so linear_kernel == cosine similarity.
        # token_pattern=None silences the "ignored" warning when a tokenizer is set.
        self.vectorizer = TfidfVectorizer(tokenizer=_tokenize, token_pattern=None)
        self.matrix = self.vectorizer.fit_transform(docs)

    def rank(self, question: str) -> list[tuple[str, float]]:
        qv = self.vectorizer.transform([question])
        scores = linear_kernel(qv, self.matrix)[0]
        return sorted(
            ((t, float(s)) for t, s in zip(self.tables, scores)),
            key=lambda x: x[1],
            reverse=True,
        )

    def top_table(self, question: str, threshold: float = 0.0):
        """Return (best_table, ranked_list). best_table is None below threshold."""
        ranked = self.rank(question)
        if not ranked or ranked[0][1] <= threshold:
            return None, ranked
        return ranked[0][0], ranked
