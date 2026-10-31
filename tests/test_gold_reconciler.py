"""Unit tests for RetroactiveReconciler."""

from sentinel.gold.config import GoldQualityContract, RollingWindowSpec
from sentinel.gold.reconciler import RetroactiveReconciler


def test_blast_radius_calculation_for_late_partition():
    """Late partition on 2026-10-25 with 7-day window invalidates 2026-10-25 through 2026-10-31."""
    contract = GoldQualityContract(
        target_table="gold_rolling_metrics",
        source_table="silver_orders",
        partition_column="order_date",
        rolling_windows=[
            RollingWindowSpec(
                name="7d_metric",
                window_size_days=7,
                metric_name="metric_7d",
                aggregation_expr="sum(amount)",
            )
        ],
    )
    reconciler = RetroactiveReconciler(contract)

    # Late partition 2026-10-25 arrives as of 2026-10-31
    blast_radius = reconciler.calculate_blast_radius(
        late_partitions=["2026-10-25"],
        as_of_date="2026-10-31",
        full_table_retention_days=365,
    )

    expected_invalidated = [
        "2026-10-25",
        "2026-10-26",
        "2026-10-27",
        "2026-10-28",
        "2026-10-29",
        "2026-10-30",
        "2026-10-31",
    ]
    assert blast_radius.invalidated_target_dates == expected_invalidated
    assert blast_radius.actual_pruned_scan_days == 7
    assert blast_radius.estimated_full_table_scan_days == 365
    assert blast_radius.scan_reduction_pct == round(((365 - 7) / 365) * 100.0, 2)
    assert (
        blast_radius.target_merge_predicate
        == "target.order_date >= '2026-10-25' AND target.order_date <= '2026-10-31'"
    )


def test_blast_radius_sql_merge_generation():
    """Verify generated Delta Lake MERGE query contains correct partition pruning predicates."""
    contract = GoldQualityContract(
        target_table="gold_rolling_metrics",
        source_table="silver_orders",
        partition_column="order_date",
        rolling_windows=[
            RollingWindowSpec(
                name="7d_metric",
                window_size_days=7,
                metric_name="metric_7d",
                aggregation_expr="sum(amount)",
            )
        ],
    )
    reconciler = RetroactiveReconciler(contract)

    blast_radius = reconciler.calculate_blast_radius(
        late_partitions=["2026-10-25"],
        as_of_date="2026-10-31",
    )
    merge_sql = reconciler.generate_delta_merge_sql(blast_radius)

    assert "MERGE INTO gold_rolling_metrics AS target" in merge_sql
    assert "target.order_date >= '2026-10-25' AND target.order_date <= '2026-10-31'" in merge_sql
    assert "target.order_date = source.order_date" in merge_sql
    assert "WHEN MATCHED THEN" in merge_sql
    assert "WHEN NOT MATCHED THEN" in merge_sql


def test_no_late_partitions_produces_zero_blast_radius():
    """Empty late partitions list should yield zero invalidated dates."""
    contract = GoldQualityContract(
        target_table="gold_rolling_metrics",
        source_table="silver_orders",
    )
    reconciler = RetroactiveReconciler(contract)

    blast_radius = reconciler.calculate_blast_radius(late_partitions=[])
    assert blast_radius.invalidated_target_dates == []
    assert blast_radius.actual_pruned_scan_days == 0
    assert blast_radius.scan_reduction_pct == 100.0


def test_blast_radius_sql_merge_generation_with_multi_entity_keys():
    """Verify MERGE query joins across all primary keys for wide/entity schemas."""
    contract = GoldQualityContract(
        target_table="gold_customer_rolling_metrics",
        source_table="silver_orders",
        partition_column="order_date",
        primary_keys=["order_date", "customer_id", "store_id"],
    )
    reconciler = RetroactiveReconciler(contract)
    blast_radius = reconciler.calculate_blast_radius(
        late_partitions=["2026-10-30"],
        as_of_date="2026-10-31",
    )
    merge_sql = reconciler.generate_delta_merge_sql(blast_radius)

    assert "target.order_date = source.order_date" in merge_sql
    assert "target.customer_id = source.customer_id" in merge_sql
    assert "target.store_id = source.store_id" in merge_sql

