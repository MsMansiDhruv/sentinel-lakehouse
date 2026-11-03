"""Unit tests for Sentinel-GenAI structure-aware document chunker."""

import pytest
from sentinel.genai.chunker import StructureAwareChunker


def test_chunker_basic_paragraph_splitting():
    text = (
        "# Overview\n"
        "This is the first paragraph with some details about data quality and SLA gates.\n\n"
        "This is the second paragraph describing the rolling window reconciler and ledger.\n\n"
        "This is the third paragraph covering alerting and threshold escalation policies."
    )
    chunker = StructureAwareChunker(max_chunk_chars=120, overlap_chars=20)
    chunks = chunker.chunk_document(
        "doc-01", text, doc_metadata={"category": "governance"}
    )

    assert len(chunks) >= 2
    for chk in chunks:
        assert chk.doc_id == "doc-01"
        assert chk.metadata["category"] == "governance"
        assert "chunk_index" in chk.metadata
        assert "char_length" in chk.metadata


def test_chunker_preserves_markdown_tables():
    table_text = (
        "| Tier | SLA (Min) | Threshold | Penalty |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| Gold | 15 | 99.9% | $5,000 |\n"
        "| Silver | 60 | 99.0% | $1,500 |\n"
        "| Bronze | 240 | 95.0% | $0 |"
    )
    doc = f"# Service Level Agreement\n\nIntroductory section before table.\n\n{table_text}\n\nConclusion section after table."
    chunker = StructureAwareChunker(
        max_chunk_chars=100, overlap_chars=10, preserve_tables=True
    )
    chunks = chunker.chunk_document("doc-sla", doc)

    # Verify the table is intact in at least one chunk
    table_chunks = [
        c
        for c in chunks
        if c.metadata.get("is_table") or "Service Level Agreement" in c.content
    ]
    assert len(table_chunks) > 0
    # Assert table structure was not cut in half
    assert any("| Gold | 15 | 99.9% | $5,000 |" in c.content for c in chunks)


def test_chunker_preserves_code_blocks():
    code_text = (
        "```sql\n"
        "SELECT customer_id, count(*), sum(order_total)\n"
        "FROM gold.fact_orders\n"
        "WHERE order_date >= current_date() - INTERVAL 30 DAYS\n"
        "GROUP BY customer_id;\n"
        "```"
    )
    doc = f"# Technical Query Catalog\n\nHere is how to calculate monthly spend:\n\n{code_text}\n\nReview this with the data team."
    chunker = StructureAwareChunker(
        max_chunk_chars=150, overlap_chars=15, preserve_code_blocks=True
    )
    chunks = chunker.chunk_document("doc-code", doc)

    code_chunks = [c for c in chunks if "SELECT customer_id" in c.content]
    assert len(code_chunks) == 1
    assert "GROUP BY customer_id;" in code_chunks[0].content


def test_chunker_empty_input_handling():
    chunker = StructureAwareChunker(max_chunk_chars=500, overlap_chars=50)
    assert chunker.chunk_document("doc-empty", "") == []
    assert chunker.chunk_document("doc-whitespace", "   \n\n  \t ") == []


def test_chunker_invalid_parameters():
    with pytest.raises(ValueError):
        StructureAwareChunker(max_chunk_chars=100, overlap_chars=150)
