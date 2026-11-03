"""Unit tests for Sentinel-GenAI Genie semantic compiler and trusted SQL catalog."""

import json
import pytest
from sentinel.genai.genie_semantic import (
    ColumnAnnotation,
    GenieSemanticCompiler,
    TableAnnotation,
    TableRelationship,
    TrustedQuery,
)


@pytest.fixture
def sample_semantic_compiler():
    compiler = GenieSemanticCompiler(
        space_name="Sentinel Orders & SLA Space",
        space_description="Enterprise data space for orders, customer SCD2, and quality ledger.",
    )

    fact_orders = TableAnnotation(
        catalog="sentinel_prod",
        schema="gold",
        table_name="fact_orders",
        description="Gold fact table containing deduplicated, cleansed customer orders.",
        primary_keys=["order_id"],
        cluster_by=["order_date", "customer_id"],
        columns=[
            ColumnAnnotation(
                name="order_id",
                data_type="string",
                description="Primary key identifier for orders",
                semantic_role="primary_key",
            ),
            ColumnAnnotation(
                name="customer_id",
                data_type="string",
                description="Foreign key reference to dim_customers",
                semantic_role="foreign_key",
            ),
            ColumnAnnotation(
                name="order_date",
                data_type="date",
                description="Date order was placed",
                semantic_role="timestamp",
            ),
            ColumnAnnotation(
                name="total_amount",
                data_type="decimal(18,2)",
                description="Total order amount after discounts",
                semantic_role="metric",
            ),
            ColumnAnnotation(
                name="order_status",
                data_type="string",
                description="Order fulfillment status",
                semantic_role="dimension",
            ),
        ],
    )

    dim_customers = TableAnnotation(
        catalog="sentinel_prod",
        schema="gold",
        table_name="dim_customers",
        description="SCD Type 2 dimensional model tracking customer profile changes.",
        primary_keys=["customer_sk"],
        cluster_by=["customer_id"],
        columns=[
            ColumnAnnotation(
                name="customer_sk",
                data_type="string",
                description="Surrogate primary key",
                semantic_role="primary_key",
            ),
            ColumnAnnotation(
                name="customer_id",
                data_type="string",
                description="Business customer key",
                semantic_role="foreign_key",
            ),
            ColumnAnnotation(
                name="region",
                data_type="string",
                description="Geographic sales region",
                semantic_role="dimension",
            ),
            ColumnAnnotation(
                name="is_current",
                data_type="boolean",
                description="True if this is the active SCD2 record",
                semantic_role="dimension",
            ),
        ],
    )

    compiler.register_table(fact_orders)
    compiler.register_table(dim_customers)

    compiler.register_relationship(
        TableRelationship(
            from_table="sentinel_prod.gold.fact_orders",
            from_column="customer_id",
            to_table="sentinel_prod.gold.dim_customers",
            to_column="customer_id",
        )
    )

    compiler.register_trusted_query(
        TrustedQuery(
            query_id="monthly_gross_revenue",
            metric_name="Gross Revenue",
            description="Computes total net revenue aggregated by calendar month for completed orders.",
            example_prompts=[
                "What was the total gross revenue by month?",
                "Monthly revenue summary",
                "Show monthly completed order sales",
            ],
            sql_template=(
                "SELECT date_trunc('month', order_date) AS order_month, sum(total_amount) AS monthly_revenue "
                "FROM sentinel_prod.gold.fact_orders "
                "WHERE order_status = 'COMPLETED' "
                "GROUP BY 1 ORDER BY 1 DESC"
            ),
            target_tables=["sentinel_prod.gold.fact_orders"],
        )
    )

    return compiler


def test_genie_space_export_structure(sample_semantic_compiler):
    config = sample_semantic_compiler.export_genie_space_config()

    assert config["name"] == "Sentinel Orders & SLA Space"
    assert len(config["tables"]) == 2
    assert len(config["relationships"]) == 1
    assert len(config["trusted_queries"]) == 1

    # Verify JSON serialization
    json_str = sample_semantic_compiler.to_json()
    assert json.loads(json_str) == config


def test_trusted_query_safety_validation():
    # Valid SELECT query passes
    safe_q = TrustedQuery(
        query_id="valid_q",
        metric_name="Valid",
        description="Safe query",
        example_prompts=["test"],
        sql_template="SELECT count(*) FROM gold.table WHERE active = true",
    )
    assert safe_q.validate_safety() is True

    # Destructive DROP / DELETE / TRUNCATE queries must raise ValueError
    unsafe_queries = [
        "DROP TABLE gold.fact_orders",
        "DELETE FROM gold.dim_customers WHERE id = 1",
        "TRUNCATE TABLE gold.ledger",
        "ALTER TABLE gold.orders ADD COLUMN hack string",
    ]
    for bad_sql in unsafe_queries:
        bad_q = TrustedQuery(
            query_id="bad_q",
            metric_name="Unsafe",
            description="Unsafe query",
            example_prompts=["test"],
            sql_template=bad_sql,
        )
        with pytest.raises(ValueError, match="forbidden DDL/DML statement"):
            bad_q.validate_safety()


def test_unity_catalog_comment_ddl(sample_semantic_compiler):
    ddl = sample_semantic_compiler.generate_unity_catalog_comments()

    assert len(ddl) > 0
    # Must contain COMMENT ON TABLE
    assert any(
        "COMMENT ON TABLE sentinel_prod.gold.fact_orders IS" in stmt for stmt in ddl
    )
    # Must contain ALTER TABLE ... ALTER COLUMN ... COMMENT
    assert any(
        "ALTER TABLE sentinel_prod.gold.fact_orders ALTER COLUMN total_amount COMMENT"
        in stmt
        for stmt in ddl
    )
