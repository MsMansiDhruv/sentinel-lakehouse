"""Unit tests for Sentinel-GenAI benchmark evaluator."""

import pytest
from sentinel.genai.chunker import DocumentChunk
from sentinel.genai.compound_router import CompoundQueryRouter, QueryIntent
from sentinel.genai.embeddings import LocalDeterministicEmbeddings
from sentinel.genai.evaluator import EvalTestCase, GenAIEvaluator
from sentinel.genai.genie_semantic import GenieSemanticCompiler, TableAnnotation
from sentinel.genai.vector_search import HybridVectorIndex


@pytest.fixture
def eval_setup():
    embedder = LocalDeterministicEmbeddings(dimension=64)
    vector_index = HybridVectorIndex(embedding_provider=embedder)
    chunks = [
        DocumentChunk(
            chunk_id="chk-sla",
            doc_id="sla-doc",
            content="Platinum SLA requires 99.99% uptime with 5-minute failure alerting.",
            metadata={"doc_type": "sla"},
        ),
    ]
    vector_index.index_chunks(chunks)

    compiler = GenieSemanticCompiler(space_name="Test", space_description="Test")
    compiler.register_table(
        TableAnnotation(
            catalog="cat", schema="sch", table_name="tab", description="Desc"
        )
    )

    router = CompoundQueryRouter(vector_index=vector_index, semantic_compiler=compiler)
    evaluator = GenAIEvaluator(router=router)
    return evaluator


def test_evaluator_benchmark_run(eval_setup):
    test_cases = [
        EvalTestCase(
            prompt="What is the total monthly sales and revenue?",
            expected_intent=QueryIntent.ANALYTICAL,
            expected_keywords=["order_month", "revenue"],
        ),
        EvalTestCase(
            prompt="What are the SLA uptime rules?",
            expected_intent=QueryIntent.POLICY_RETRIEVAL,
            expected_keywords=["uptime", "99.99%"],
        ),
    ]

    scorecard = eval_setup.evaluate(test_cases)

    assert scorecard.total_cases == 2
    assert scorecard.intent_accuracy == 1.0
    assert scorecard.avg_context_relevance > 0.0
    assert scorecard.guardrail_pass_rate == 1.0
    assert scorecard.avg_latency_ms >= 0.0

    # Verify markdown rendering
    md = scorecard.to_markdown()
    assert "# Sentinel-GenAI Benchmark Scorecard" in md
    assert "**Intent Accuracy**: 100.0%" in md
    assert "PASS" in md


def test_evaluator_empty_cases(eval_setup):
    with pytest.raises(ValueError):
        eval_setup.evaluate([])
