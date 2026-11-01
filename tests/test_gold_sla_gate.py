"""Unit tests for DeltaMetadataSlaGate."""

from datetime import datetime, timedelta

from sentinel.gold.config import GoldQualityContract, SlaStatus
from sentinel.gold.sla_gate import DeltaMetadataSlaGate


def test_on_time_partition_arrival():
    """Valid partition present on time should return ON_TIME and no breach."""
    contract = GoldQualityContract(
        target_table="gold_orders",
        source_table="silver_orders",
        sla_grace_period_hours=4,
    )
    gate = DeltaMetadataSlaGate(contract)

    # Evaluating partition 2026-10-30 on 2026-10-31 at 02:00 AM (within 4h grace period)
    eval_ts = datetime(2026, 10, 31, 2, 0, 0)
    result = gate.evaluate_arrival(
        target_date="2026-10-30",
        available_partitions={"2026-10-29", "2026-10-30"},
        partition_row_counts={"2026-10-30": 15000},
        evaluation_timestamp=eval_ts,
    )

    assert result.status == SlaStatus.ON_TIME
    assert not result.is_breached
    assert result.missing_partitions == []
    assert result.row_count == 15000
    assert result.dbu_savings_pct > 99.0


def test_missing_partition_within_grace_period():
    """Missing partition before the deadline should be flagged LATE_ARRIVING."""
    contract = GoldQualityContract(
        target_table="gold_orders",
        source_table="silver_orders",
        sla_grace_period_hours=4,
    )
    gate = DeltaMetadataSlaGate(contract)

    # 2026-10-31 at 01:00 AM (deadline is 04:00 AM)
    eval_ts = datetime(2026, 10, 31, 1, 0, 0)
    result = gate.evaluate_arrival(
        target_date="2026-10-30",
        available_partitions={"2026-10-29"},  # 2026-10-30 has NOT arrived yet
        evaluation_timestamp=eval_ts,
    )

    assert result.status == SlaStatus.LATE_ARRIVING
    assert not result.is_breached
    assert result.missing_partitions == ["2026-10-30"]


def test_missing_partition_sla_breached():
    """Missing partition after the deadline should trigger SLA_BREACHED."""
    contract = GoldQualityContract(
        target_table="gold_orders",
        source_table="silver_orders",
        sla_grace_period_hours=4,
    )
    gate = DeltaMetadataSlaGate(contract)

    # 2026-10-31 at 06:00 AM (deadline was 04:00 AM)
    eval_ts = datetime(2026, 10, 31, 6, 0, 0)
    result = gate.evaluate_arrival(
        target_date="2026-10-30",
        available_partitions={"2026-10-29"},
        evaluation_timestamp=eval_ts,
    )

    assert result.status == SlaStatus.SLA_BREACHED
    assert result.is_breached
    assert result.missing_partitions == ["2026-10-30"]


def test_volume_anomaly_detected():
    """Partition with row count below minimum should flag VOLUME_ANOMALY."""
    contract = GoldQualityContract(
        target_table="gold_orders",
        source_table="silver_orders",
        min_expected_rows=100,
    )
    gate = DeltaMetadataSlaGate(contract)

    result = gate.evaluate_arrival(
        target_date="2026-10-30",
        available_partitions={"2026-10-30"},
        partition_row_counts={"2026-10-30": 5},  # Only 5 rows arrived
    )

    assert result.status == SlaStatus.VOLUME_ANOMALY
    assert result.is_breached
    assert result.row_count == 5
