"""Hybrid Vector Search index supporting dense vector similarity, sparse BM25, and RRF."""

from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass
from typing import Any

from sentinel.genai.chunker import DocumentChunk
from sentinel.genai.embeddings import EmbeddingProvider


@dataclass
class SearchResult:
    """Retrieved search result with score and ranking metrics."""

    chunk: DocumentChunk
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    match_type: str = "hybrid"


class HybridVectorIndex:
    """In-memory hybrid vector search engine simulating Databricks Mosaic AI Vector Search.

    Combines dense cosine similarity with sparse BM25 lexical scoring via Reciprocal Rank Fusion.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        rrf_k: int = 60,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.rrf_k = rrf_k
        self._chunks: list[DocumentChunk] = []
        self._embeddings: list[list[float]] = []

        # BM25 statistics
        self._doc_token_counts: list[int] = []
        self._avg_doc_len: float = 0.0
        self._term_doc_freq: dict[str, int] = collections.defaultdict(int)
        self._chunk_term_counts: list[collections.Counter[str]] = []

    def index_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Embed and register document chunks into the index."""
        if not chunks:
            return

        texts = [chunk.content for chunk in chunks]
        embeddings = self.embedding_provider.embed_batch(texts)

        for chunk, emb in zip(chunks, embeddings):
            self._chunks.append(chunk)
            self._embeddings.append(emb)

            # BM25 token analysis
            tokens = self._tokenize(chunk.content)
            self._doc_token_counts.append(len(tokens))
            term_counts: collections.Counter[str] = collections.Counter(tokens)
            self._chunk_term_counts.append(term_counts)

            for term in term_counts:
                self._term_doc_freq[term] += 1

        total_tokens = sum(self._doc_token_counts)
        self._avg_doc_len = total_tokens / max(1, len(self._chunks))

    def search(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Query the index using 'hybrid', 'dense', or 'sparse' retrieval."""
        if not self._chunks:
            return []

        mode = mode.lower()
        if mode not in ("hybrid", "dense", "sparse"):
            raise ValueError("Mode must be 'hybrid', 'dense', or 'sparse'.")

        candidate_indices = [
            i
            for i, chunk in enumerate(self._chunks)
            if self._matches_filter(chunk, filters)
        ]
        if not candidate_indices:
            return []

        # 1. Dense retrieval
        dense_scores: list[tuple[int, float]] = []
        if mode in ("hybrid", "dense"):
            q_emb = self.embedding_provider.embed_text(query)
            for idx in candidate_indices:
                sim = self._cosine_similarity(q_emb, self._embeddings[idx])
                dense_scores.append((idx, sim))
            dense_scores.sort(key=lambda x: x[1], reverse=True)

        # 2. Sparse BM25 retrieval
        sparse_scores: list[tuple[int, float]] = []
        if mode in ("hybrid", "sparse"):
            q_tokens = self._tokenize(query)
            for idx in candidate_indices:
                score = self._compute_bm25(q_tokens, idx)
                sparse_scores.append((idx, score))
            sparse_scores.sort(key=lambda x: x[1], reverse=True)

        if mode == "dense":
            return [
                SearchResult(
                    chunk=self._chunks[idx],
                    score=score,
                    dense_rank=rank + 1,
                    match_type="dense",
                )
                for rank, (idx, score) in enumerate(dense_scores[:top_k])
            ]

        if mode == "sparse":
            return [
                SearchResult(
                    chunk=self._chunks[idx],
                    score=score,
                    sparse_rank=rank + 1,
                    match_type="sparse",
                )
                for rank, (idx, score) in enumerate(sparse_scores[:top_k])
            ]

        # 3. Reciprocal Rank Fusion (RRF) for Hybrid Mode
        dense_rank_map = {idx: rank + 1 for rank, (idx, _) in enumerate(dense_scores)}
        sparse_rank_map = {idx: rank + 1 for rank, (idx, _) in enumerate(sparse_scores)}

        rrf_scores: dict[int, float] = {}
        for idx in candidate_indices:
            score = 0.0
            if idx in dense_rank_map:
                score += 1.0 / (self.rrf_k + dense_rank_map[idx])
            if idx in sparse_rank_map:
                score += 1.0 / (self.rrf_k + sparse_rank_map[idx])
            rrf_scores[idx] = score

        ranked_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                chunk=self._chunks[idx],
                score=score,
                dense_rank=dense_rank_map.get(idx),
                sparse_rank=sparse_rank_map.get(idx),
                match_type="hybrid",
            )
            for idx, score in ranked_results[:top_k]
        ]

    def _matches_filter(
        self, chunk: DocumentChunk, filters: dict[str, Any] | None
    ) -> bool:
        if not filters:
            return True
        for key, expected in filters.items():
            if chunk.metadata.get(key) != expected:
                return False
        return True

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2))
        return max(-1.0, min(1.0, dot))

    def _compute_bm25(
        self, query_tokens: list[str], doc_idx: int, k1: float = 1.5, b: float = 0.75
    ) -> float:
        if not query_tokens:
            return 0.0
        doc_len = self._doc_token_counts[doc_idx]
        term_counts = self._chunk_term_counts[doc_idx]
        n_docs = len(self._chunks)
        score = 0.0

        for t in query_tokens:
            if t not in term_counts:
                continue
            tf = term_counts[t]
            df = self._term_doc_freq[t]
            # Standard Lucene/BM25 IDF formula
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            num = tf * (k1 + 1.0)
            den = tf + k1 * (1.0 - b + b * (doc_len / max(1.0, self._avg_doc_len)))
            score += idf * (num / den)

        return score
