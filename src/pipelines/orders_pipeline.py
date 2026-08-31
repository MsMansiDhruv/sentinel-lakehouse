# ============================================================
# SCD TYPE 1
# SENTINEL COMMERCE
# Lakeflow Spark Declarative Pipeline
#
# Flow:
# Landing → Bronze → Typed → DQ → Valid / Quarantine
#
# Data Quality:
# Lakeflow Expectations
# ============================================================

from pyspark import pipelines as dp
from pyspark.sql import functions as F

# ============================================================
# 1. CONFIGURATION
# ============================================================

SOURCE_PATH = "/Volumes/sentinel_dev/landing/source_files/orders"

SCHEMA_PATH = (
    "/Volumes/sentinel_dev/landing/source_files/"
    "_schemas/lakeflow_orders"
)

# ============================================================
# 2. BRONZE — AUTO LOADER
# ============================================================

@dp.table(
    name="bronze_orders",
    comment="Raw commerce orders incrementally ingested using Auto Loader"
)
def bronze_orders():

    return (
        spark.readStream
            .format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option(
                "cloudFiles.schemaLocation",
                SCHEMA_PATH
            )
            .option(
                "rescuedDataColumn",
                "_rescued_data"
            )
            .load(SOURCE_PATH)

            .selectExpr(
                "*",
                "_metadata.file_path AS source_file",
                "_metadata.file_name AS source_file_name",
                "_metadata.file_modification_time "
                "AS source_file_modified_at"
            )

            .withColumn(
                "ingested_at",
                F.current_timestamp()
            )
    )


# ============================================================
# 3. TYPED STAGING VIEW
# ============================================================

@dp.temporary_view(
    name="orders_typed",
    comment="Orders with safe business type conversions"
)
def orders_typed():

    return (
        spark.readStream
            .table("bronze_orders")

            .withColumn(
                "quantity_clean",
                F.expr(
                    "try_cast(quantity AS INT)"
                )
            )

            .withColumn(
                "unit_price_clean",
                F.expr(
                    "try_cast(unit_price AS DECIMAL(18,2))"
                )
            )

            .withColumn(
                "total_amount_clean",
                F.expr(
                    "try_cast(total_amount AS DECIMAL(18,2))"
                )
            )

            .withColumn(
                "order_timestamp_clean",
                F.expr(
                    "try_cast(order_timestamp AS TIMESTAMP)"
                )
            )
    )

# ============================================================
# 4. DATA QUALITY CONTRACT
# ============================================================

ORDER_RULES = {

    "order_id_required":
        "order_id IS NOT NULL",

    "customer_id_required":
        "customer_id IS NOT NULL",

    "product_id_required":
        "product_id IS NOT NULL",

    "valid_quantity":
        """
        quantity_clean IS NOT NULL
        AND quantity_clean > 0
        """,

    "valid_unit_price":
        """
        unit_price_clean IS NOT NULL
        AND unit_price_clean >= 0
        """,

    "valid_total_amount":
        """
        total_amount_clean IS NOT NULL
        AND total_amount_clean >= 0
        """,

    "valid_order_status":
        """
        order_status IN (
            'PLACED',
            'CONFIRMED',
            'SHIPPED',
            'DELIVERED',
            'CANCELLED'
        )
        """,

    "valid_payment_method":
        """
        payment_method IN (
            'UPI',
            'CREDIT_CARD',
            'DEBIT_CARD',
            'NET_BANKING',
            'COD'
        )
        """,

    "valid_order_timestamp":
        """
        order_timestamp_clean IS NOT NULL
        AND order_timestamp_clean <= current_timestamp()
        """,

    "valid_order_amount":
        """
        abs(
            total_amount_clean -
            (quantity_clean * unit_price_clean)
        ) <= 0.01
        """
}


# ============================================================
# 5. BUILD QUARANTINE CONDITION
# ============================================================

VALID_RECORD_EXPRESSION = " AND ".join(
    f"({rule})"
    for rule in ORDER_RULES.values()
)


FAILED_RULE_EXPRESSIONS = [

    F.when(
        ~F.expr(rule_expression),
        F.lit(rule_name)
    )

    for rule_name, rule_expression
    in ORDER_RULES.items()
]


# ============================================================
# 6. DQ STAGING
#
# IMPORTANT:
# expect_all = measure violations but KEEP records.
#
# We need bad records to survive here so they can be
# routed into quarantine.
# ============================================================

@dp.table(
    name="orders_dq_staging",
    temporary=True,
    comment="Order quality evaluation staging dataset"
)
@dp.expect_all(ORDER_RULES)
def orders_dq_staging():

    return (
        spark.readStream
            .table("orders_typed")

            .withColumn(
                "is_valid",
                F.expr(VALID_RECORD_EXPRESSION)
            )

            .withColumn(
                "failed_rules",
                F.array_compact(
                    F.array(
                        *FAILED_RULE_EXPRESSIONS
                    )
                )
            )
    )


# ============================================================
# 7. VALID SILVER ORDERS
# ============================================================

@dp.table(
    name="silver_orders_validated",
    comment="Orders satisfying the Silver data quality contract"
)
def silver_orders_validated():

    return (
        spark.readStream
            .table("orders_dq_staging")

            .filter(
                F.col("is_valid")
            )

            .drop(
                "is_valid",
                "failed_rules"
            )
    )

# ============================================================
# 8. QUARANTINE
# ============================================================

@dp.table(
    name="orders_quarantine",
    comment="Orders rejected by the Silver data quality contract"
)
def orders_quarantine():

    return (
        spark.readStream
            .table("orders_dq_staging")

            .filter(
                ~F.col("is_valid")
            )
    )


# ===========================================
# 9. SILVER TABLE
#
# Maintained using Lakeflow AUTO CDC.
# One current record per order_id.
# ============================================================

dp.create_streaming_table(
    name="silver_orders_current",
    comment="Current validated state of each commerce order"
)

dp.create_auto_cdc_flow(
    target="silver_orders_current",

    source="silver_orders_validated",

    keys=["order_id"],

    sequence_by=F.col("order_timestamp_clean"),

    stored_as_scd_type=1
)

# ============================================================
# 10. ORDER HISTORY — SCD TYPE 2
#
# Purpose:
# Preserve historical versions of each order.
#
# Business key:
#   order_id
#
# Sequence:
#   order_timestamp_clean
#
# Unlike Type 1, previous versions are NOT overwritten.
# ============================================================

dp.create_streaming_table(
    name="silver_orders_history",
    comment="Historical order states maintained using SCD Type 2"
)


dp.create_auto_cdc_flow(
    target="silver_orders_history",

    source="silver_orders_validated",

    keys=["order_id"],

    sequence_by=F.col("order_timestamp_clean"),

    stored_as_scd_type=2
)


