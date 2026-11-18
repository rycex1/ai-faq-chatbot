"""BM25 keyword retrieval over document chunks (local, no embeddings or external service)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .chunking import Chunk

STOPWORDS = frozenset(
    """a an and are as at be but by can do does for from have how i if in is it its me my of on or our
    please so than that the their them then there these they this to was we what when where which who
    will with you your yours us""".split()
)


def stem(word: str) -> str:
    """Very small suffix stemmer so 'parking'/'park', 'opening'/'open' and 'cakes'/'cake' match.

    It is deliberately crude; it only has to map related words to the same token.
    """
    for suffix in ("ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    else:
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("es") and len(word) > 4 and (word[-3] in "sxz" or word.endswith(("ches", "shes"))):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    """Lower-case, stemmed word tokens without stopwords."""
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("Cannot build an index with no chunks")
        self.chunks = chunks
        # Heading and title are indexed too, so "catering" finds the catering page's sections.
        corpus = [tokenize(f"{c.title} {c.heading} {c.heading} {c.text}") for c in chunks]
        self._bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 4, min_score: float = 0.0, rel_cutoff: float = 0.3) -> list[Hit]:
        """Top chunks for `query`. Hits scoring below `rel_cutoff` x the best score are dropped,
        so one strong match is not padded out with chunks that only share a common word."""
        terms = tokenize(query)
        if not terms:
            return []
        scores = self._bm25.get_scores(terms)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        if not ranked or scores[ranked[0]] <= min_score:
            return []
        floor = max(min_score, scores[ranked[0]] * rel_cutoff)
        return [Hit(self.chunks[i], float(scores[i])) for i in ranked if scores[i] >= floor]
