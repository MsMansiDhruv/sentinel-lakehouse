"""Unit tests for Sentinel-GenAI hybrid vector search index."""

import pytest
from sentinel.genai.chunker import DocumentChunk
from sentinel.genai.embeddings import LocalDeterministicEmbeddings
from sentinel.genai.vector_search import HybridVectorIndex


@pytest.fixture
def sample_chunks():
    return [
        DocumentChunk(
            chunk_id="chk-01",
            doc_id="sla-doc",
            content="Platinum SLA requires 99.99% pipeline uptime and sub-10-second alerting on fraud anomaly spikes.",
            metadata={"tier": "platinum", "department": "security"},
        ),
        DocumentChunk(
            chunk_id="chk-02",
            doc_id="sla-doc",
            content="Gold SLA requires 99.9% uptime with 15-minute reconciliation and automated quarantine dead-letter routing.",
            metadata={"tier": "gold", "department": "operations"},
        ),
        DocumentChunk(
            chunk_id="chk-03",
            doc_id="dict-doc",
            content="The customer dimension table tracks SCD Type 2 attributes including risk tier, billing zip code, and loyalty status.",
            metadata={"tier": "standard", "department": "analytics"},
        ),
        DocumentChunk(
            chunk_id="chk-04",
            doc_id="dict-doc",
            content="The fact orders table stores order timestamp, net revenue, currency, and discount deductions.",
            metadata={"tier": "standard", "department": "analytics"},
        ),
    ]


def test_hybrid_search_rrf_retrieval(sample_chunks):
    embedder = LocalDeterministicEmbeddings(dimension=64)
    index = HybridVectorIndex(embedding_provider=embedder, rrf_k=60)
    index.index_chunks(sample_chunks)

    results = index.search(
        "platinum uptime alerting fraud spikes", top_k=2, mode="hybrid"
    )
    assert len(results) == 2
    # First result must be chunk 1
    assert results[0].chunk.chunk_id == "chk-01"
    assert results[0].dense_rank is not None
    assert results[0].sparse_rank is not None
    assert results[0].match_type == "hybrid"


def test_metadata_filtering(sample_chunks):
    embedder = LocalDeterministicEmbeddings(dimension=64)
    index = HybridVectorIndex(embedding_provider=embedder)
    index.index_chunks(sample_chunks)

    # Filter strictly for department = operations
    results = index.search("uptime", top_k=5, filters={"department": "operations"})
    assert len(results) == 1
    assert results[0].chunk.chunk_id == "chk-02"
    assert results[0].chunk.metadata["tier"] == "gold"


def test_search_modes(sample_chunks):
    embedder = LocalDeterministicEmbeddings(dimension=64)
    index = HybridVectorIndex(embedding_provider=embedder)
    index.index_chunks(sample_chunks)

    dense_res = index.search("orders table revenue", top_k=2, mode="dense")
    assert len(dense_res) == 2
    assert dense_res[0].match_type == "dense"

    sparse_res = index.search("SCD Type 2 attributes risk tier", top_k=2, mode="sparse")
    assert len(sparse_res) == 2
    assert sparse_res[0].match_type == "sparse"
    assert sparse_res[0].chunk.chunk_id == "chk-03"


def test_empty_index_search():
    embedder = LocalDeterministicEmbeddings(dimension=32)
    index = HybridVectorIndex(embedding_provider=embedder)
    assert index.search("test") == []
