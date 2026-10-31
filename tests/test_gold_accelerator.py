"""Integrated end-to-end unit tests for SentinelGoldAccelerator."""

from sentinel.gold.accelerator import SentinelGoldAccelerator
from sentinel.gold.config import (
    GatingPolicy,
    GoldQualityContract,
    RollingWindowSpec,
    SlaStatus,
)


def test_accelerator_pipeline_clean_run():
    """Verify clean pipeline execution when all partitions and windows are complete."""
    contract = GoldQualityContract(
        target_table="gold_order_kpis",
        source_table="silver_orders",
        gating_policy=GatingPolicy.DEGRADED_WITH_MARKER,
        rolling_windows=[
            RollingWindowSpec(
                name="7d_revenue",
                window_size_days=7,
                metric_name="revenue_7d",
                aggregation_expr="sum(amount)",
            )
        ],
    )
    accelerator = SentinelGoldAccelerator(contract)

    partitions = {
        "2026-10-25",
        "2026-10-26",
        "2026-10-27",
        "2026-10-28",
        "2026-10-29",
        "2026-10-30",
        "2026-10-31",
    }
    report = accelerator.run_pipeline_check(
        target_date="2026-10-31",
        available_partitions=partitions,
    )

    assert report.can_proceed
    assert report.sla_result.status == SlaStatus.ON_TIME
    assert report.window_results["7d_revenue"].is_complete
    assert report.quality_markers["_dq_7d_revenue_complete"] is True
    assert report.reconciliation_plan is None

    # Verify audit ledger recorded events
    summary = accelerator.ledger.get_summary()
    assert summary["total_events"] == 2
    assert summary["total_breaches"] == 0
    assert summary["average_scan_reduction_pct"] > 99.0


def test_accelerator_pipeline_handles_late_arrival_reconciliation():
    """Verify that late partition triggers automated blast radius plan in pipeline check."""
    contract = GoldQualityContract(
        target_table="gold_order_kpis",
        source_table="silver_orders",
        gating_policy=GatingPolicy.DEGRADED_WITH_MARKER,
        rolling_windows=[
            RollingWindowSpec(
                name="7d_revenue",
                window_size_days=7,
                metric_name="revenue_7d",
                aggregation_expr="sum(amount)",
            )
        ],
    )
    accelerator = SentinelGoldAccelerator(contract)

    # Today is 2026-10-31. Suppose partition 2026-10-25 was late and just arrived today.
    partitions = {
        "2026-10-25",
        "2026-10-26",
        "2026-10-27",
        "2026-10-28",
        "2026-10-29",
        "2026-10-30",
        "2026-10-31",
    }
    report = accelerator.run_pipeline_check(
        target_date="2026-10-31",
        available_partitions=partitions,
        late_partitions=["2026-10-25"],
    )

    assert report.can_proceed
    assert report.reconciliation_plan is not None
    assert len(report.reconciliation_plan.invalidated_target_dates) == 7
    assert report.delta_merge_sql is not None
    assert "MERGE INTO gold_order_kpis AS target" in report.delta_merge_sql

    summary = accelerator.ledger.get_summary()
    assert summary["reconciliations_triggered"] == 1
