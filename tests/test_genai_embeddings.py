"""Unit tests for Sentinel-GenAI embedding providers."""

import math
import pytest
from sentinel.genai.embeddings import DatabricksEmbeddings, LocalDeterministicEmbeddings


def test_local_embeddings_dimension_and_normalization():
    embedder = LocalDeterministicEmbeddings(dimension=64)
    assert embedder.dimension == 64

    vec = embedder.embed_text("Databricks Lakehouse with Unity Catalog and Delta Lake")
    assert len(vec) == 64

    # Assert L2 normalized: sum of squares == 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    assert pytest.approx(norm, 1e-4) == 1.0


def test_local_embeddings_semantic_affinity():
    embedder = LocalDeterministicEmbeddings(dimension=128)

    vec_a = embedder.embed_text(
        "financial fraud detection in real-time streaming transactions"
    )
    vec_b = embedder.embed_text(
        "financial fraud alerting in stream transaction scoring"
    )
    vec_c = embedder.embed_text(
        "astronomy astrophysics telescope star constellation galaxy"
    )

    def cosine(u, v):
        return sum(x * y for x, y in zip(u, v))

    sim_ab = cosine(vec_a, vec_b)
    sim_ac = cosine(vec_a, vec_c)

    # Relevant documents should have significantly higher similarity than completely unrelated topics
    assert sim_ab > sim_ac
    assert sim_ab > 0.25
    assert sim_ac < 0.20


def test_local_embeddings_empty_string():
    embedder = LocalDeterministicEmbeddings(dimension=32)
    vec = embedder.embed_text("")
    assert vec == [0.0] * 32


def test_local_embeddings_batch_processing():
    embedder = LocalDeterministicEmbeddings(dimension=48)
    texts = ["Order processing", "Customer retention", "Inventory reorder"]
    batch = embedder.embed_batch(texts)
    assert len(batch) == 3
    for vec in batch:
        assert len(vec) == 48


def test_databricks_embeddings_mock_request(monkeypatch):
    embedder = DatabricksEmbeddings(
        endpoint_url="https://test.cloud.databricks.com/serving-endpoints/test/invocations",
        token="dapi-test-token",
        dimension=4,
    )

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]}'

    def mock_urlopen(req, timeout):
        assert req.get_header("Authorization") == "Bearer dapi-test-token"
        return MockResponse()

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    res = embedder.embed_text("test prompt")
    assert res == [0.1, 0.2, 0.3, 0.4]
