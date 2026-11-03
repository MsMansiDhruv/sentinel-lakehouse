"""Embedding provider abstractions and Databricks Foundation Model interfaces."""

from __future__ import annotations

import abc
import hashlib
import json
import math
import urllib.error
import urllib.request
from typing import Sequence


class EmbeddingProvider(abc.ABC):
    """Abstract interface for text embedding models."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""

    @abc.abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate a normalized embedding vector for a single string."""

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate normalized embedding vectors for multiple strings."""
        return [self.embed_text(t) for t in texts]


class LocalDeterministicEmbeddings(EmbeddingProvider):
    """Zero-dependency deterministic embedding generator for local development and CI testing.

    Generates L2-normalized pseudo-semantic vectors based on character n-grams and token hashing.
    """

    def __init__(self, dimension: int = 128) -> None:
        if dimension <= 0:
            raise ValueError("Dimension must be positive.")
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        cleaned = text.lower().strip()
        if not cleaned:
            return vec

        # Token and bigram hashed projections
        tokens = cleaned.split()
        for i, token in enumerate(tokens):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            idx = h % self._dim
            sign = 1.0 if ((h >> 4) & 1) == 0 else -1.0
            vec[idx] += sign * (1.0 + 1.0 / (1.0 + i * 0.1))

            # Bigram interaction
            if i > 0:
                bi = f"{tokens[i - 1]}_{token}"
                h_bi = int(hashlib.sha256(bi.encode()).hexdigest(), 16)
                idx_bi = h_bi % self._dim
                vec[idx_bi] += 1.5 if ((h_bi >> 3) & 1) == 0 else -1.5

        # Character trigrams for morphological similarity
        for j in range(len(cleaned) - 2):
            tri = cleaned[j : j + 3]
            h_tri = int(hashlib.sha1(tri.encode()).hexdigest(), 16)
            idx_tri = h_tri % self._dim
            vec[idx_tri] += 0.35 if ((h_tri >> 2) & 1) == 0 else -0.35

        # L2 Normalization
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        return vec


class DatabricksEmbeddings(EmbeddingProvider):
    """Client for Databricks Foundation Model Serving endpoints (e.g. databricks-bge-large-en)."""

    def __init__(
        self,
        endpoint_url: str,
        token: str,
        dimension: int = 1024,
        timeout_seconds: int = 30,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.token = token
        self._dim = dimension
        self.timeout_seconds = timeout_seconds

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_text(self, text: str) -> list[float]:
        batch = self.embed_batch([text])
        return batch[0] if batch else [0.0] * self._dim

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        payload = json.dumps({"input": list(texts)}).encode("utf-8")
        req = urllib.request.Request(
            url=self.endpoint_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
                # Handle standard Databricks Foundation Model embeddings payload
                if "data" in body:
                    return [item["embedding"] for item in body["data"]]
                if "embeddings" in body:
                    return body["embeddings"]
                raise ValueError(
                    f"Unrecognized embeddings response format: {body.keys()}"
                )
        except urllib.error.URLError as err:
            raise RuntimeError(
                f"Databricks embedding serving request failed: {err}"
            ) from err
