"""Tests for Genie Space semantic configuration and Unity Catalog DDL generator."""

import json

from sentinel.genie_bench.space import (
    GenieDimension,
    GenieJoin,
    GenieMeasure,
    GenieSpace,
    GenieTable,
)


def test_genie_space_serialization_and_unity_catalog_ddl() -> None:
    orders_table = GenieTable(
        catalog="main",
        schema="gold",
        table_name="orders",
        description="Cleaned, reconciled gold orders fact table.",
        dimensions=[
            GenieDimension(
                column_name="order_id",
                data_type="STRING",
                description="Unique identifier for order.",
                synonyms=["invoice_id", "transaction_ref"],
            ),
            GenieDimension(
                column_name="order_date",
                data_type="DATE",
                description="Calendar date order was placed.",
                synonyms=["purchase_date", "day"],
            ),
        ],
        measures=[
            GenieMeasure(
                name="total_revenue",
                expression="SUM(amount)",
                description="Total gross revenue in USD.",
                synonyms=["sales", "gross_volume"],
                format_type="currency",
            )
        ],
    )

    customers_table = GenieTable(
        catalog="main",
        schema="gold",
        table_name="customers",
        description="Customer dimension table.",
        dimensions=[
            GenieDimension(
                column_name="customer_id",
                data_type="STRING",
                description="Primary key for customer.",
            ),
            GenieDimension(
                column_name="region",
                data_type="STRING",
                description="Geographical operating region.",
            ),
        ],
    )

    joins = [
        GenieJoin(
            from_table="main.gold.orders",
            to_table="main.gold.customers",
            join_type="LEFT",
            on_clause="main.gold.orders.customer_id = main.gold.customers.customer_id",
        )
    ]

    space = GenieSpace(
        space_id="genie-gold-commerce",
        name="Commerce Analytics Space",
        description="Databricks AI/BI semantic layer for commercial metrics.",
        tables=[orders_table, customers_table],
        joins=joins,
        curated_instructions=[
            "Always filter cancelled orders where status = 'CANCELLED'"
        ],
    )

    # Test JSON export
    space_json = space.to_json()
    parsed = json.loads(space_json)
    assert parsed["space_id"] == "genie-gold-commerce"
    assert len(parsed["tables"]) == 2
    assert len(parsed["joins"]) == 1

    # Test Unity Catalog DDL statements
    ddl = space.generate_unity_catalog_ddl()
    assert len(ddl) >= 4  # 2 table comments + column comments
    assert any("COMMENT ON TABLE main.gold.orders" in stmt for stmt in ddl)
    assert any("COMMENT ON COLUMN main.gold.orders.order_id" in stmt for stmt in ddl)
    assert any("Synonyms: invoice_id, transaction_ref" in stmt for stmt in ddl)
