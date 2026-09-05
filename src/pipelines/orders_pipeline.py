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
from sentinel.quality.orders import ORDER_RULES

# ============================================================
# 1. CONFIGURATION
# ============================================================
CATALOG = spark.conf.get("sentinel.catalog")

LANDING_VOLUME = f"/Volumes/{CATALOG}/landing/source_files"

SOURCE_PATH = f"{LANDING_VOLUME}/orders"

SCHEMA_PATH = f"{LANDING_VOLUME}/_schemas/lakeflow_orders"
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

# Moved the ORDER_RULES to quality/orders.py


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


