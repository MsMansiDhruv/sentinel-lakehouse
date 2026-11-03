"""Unit tests for Sentinel-GenAI compound AI router and response synthesizer."""

import pytest
from sentinel.genai.chunker import DocumentChunk
from sentinel.genai.compound_router import CompoundQueryRouter, QueryIntent
from sentinel.genai.embeddings import LocalDeterministicEmbeddings
from sentinel.genai.genie_semantic import (
    ColumnAnnotation,
    GenieSemanticCompiler,
    TableAnnotation,
    TrustedQuery,
)
from sentinel.genai.vector_search import HybridVectorIndex


@pytest.fixture
def compound_system():
    # 1. Vector Index setup
    embedder = LocalDeterministicEmbeddings(dimension=64)
    vector_index = HybridVectorIndex(embedding_provider=embedder)
    chunks = [
        DocumentChunk(
            chunk_id="sla-01",
            doc_id="sla-contract",
            content="Platinum SLA uptime requirements: 99.99% pipeline availability with penalty terms of $10,000 per hour of downtime.",
            metadata={"doc_type": "sla", "tier": "platinum"},
        ),
        DocumentChunk(
            chunk_id="policy-02",
            doc_id="security-policy",
            content="Security policy and GDPR rules: PII encryption and data masking are mandatory on customer and email records.",
            metadata={"doc_type": "policy", "scope": "gdpr"},
        ),
    ]
    vector_index.index_chunks(chunks)

    # 2. Semantic Compiler setup
    compiler = GenieSemanticCompiler(
        space_name="Production Lakehouse Space",
        space_description="Enterprise semantic data space",
    )
    table = TableAnnotation(
        catalog="sentinel",
        schema="gold",
        table_name="fact_orders",
        description="Orders fact table",
        columns=[
            ColumnAnnotation(
                name="order_id", data_type="string", description="Order ID"
            ),
            ColumnAnnotation(
                name="total_amount",
                data_type="decimal(18,2)",
                description="Total order amount",
            ),
        ],
    )
    compiler.register_table(table)
    compiler.register_trusted_query(
        TrustedQuery(
            query_id="monthly_revenue",
            metric_name="Monthly Revenue",
            description="Computes monthly revenue",
            example_prompts=["Show monthly revenue", "total sales by month"],
            sql_template="SELECT date_trunc('month', order_date) AS month, sum(total_amount) AS rev FROM sentinel.gold.fact_orders GROUP BY 1",
            target_tables=["sentinel.gold.fact_orders"],
        )
    )

    router = CompoundQueryRouter(vector_index=vector_index, semantic_compiler=compiler)
    return router


def test_intent_classification(compound_system):
    # Pure analytical
    assert (
        compound_system.classify_intent("What is the total revenue by month?")
        == QueryIntent.ANALYTICAL
    )

    # Pure policy
    assert (
        compound_system.classify_intent(
            "What are the GDPR rules on customer email masking?"
        )
        == QueryIntent.POLICY_RETRIEVAL
    )

    # Hybrid: both revenue and SLA penalty
    assert (
        compound_system.classify_intent(
            "What is the monthly revenue and what are the SLA penalty clauses?"
        )
        == QueryIntent.HYBRID
    )


def test_analytical_execution(compound_system):
    response = compound_system.route_and_execute("Show monthly revenue")
    assert response.intent == QueryIntent.ANALYTICAL
    assert response.sql_query is not None
    assert "sentinel.gold.fact_orders" in response.sql_query
    assert response.sql_results is not None
    assert len(response.sql_results) > 0
    assert "Analytical Findings" in response.answer


def test_unstructured_policy_execution(compound_system):
    response = compound_system.route_and_execute(
        "What are the GDPR rules on customer masking?"
    )
    assert response.intent == QueryIntent.POLICY_RETRIEVAL
    assert len(response.retrieved_chunks) > 0
    assert response.retrieved_chunks[0].chunk.chunk_id == "policy-02"
    assert "security-policy" in response.answer


def test_hybrid_compound_execution(compound_system):
    response = compound_system.route_and_execute(
        "Calculate monthly revenue and check platinum SLA penalty terms"
    )
    assert response.intent == QueryIntent.HYBRID
    assert response.sql_results is not None
    assert len(response.retrieved_chunks) > 0
    assert "Analytical Findings" in response.answer
    assert "Policy & SLA Context" in response.answer
    assert response.guardrail_passed is True
