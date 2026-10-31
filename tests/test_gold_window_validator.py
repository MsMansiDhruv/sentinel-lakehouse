"""Unit tests for RollingWindowValidator."""

import pytest

from sentinel.gold.config import GatingPolicy, RollingWindowSpec
from sentinel.gold.window_validator import (
    IncompleteWindowError,
    RollingWindowValidator,
)


def test_complete_seven_day_window():
    """All 7 days present should return completeness_score 1.0 and PROCEED_CLEAN."""
    spec = RollingWindowSpec(
        name="7d_revenue",
        window_size_days=7,
        metric_name="rolling_revenue_7d",
        aggregation_expr="sum(amount)",
    )
    validator = RollingWindowValidator(policy=GatingPolicy.DEGRADED_WITH_MARKER)

    # 7 contiguous days up to 2026-10-31: 25, 26, 27, 28, 29, 30, 31
    partitions = {
        "2026-10-25",
        "2026-10-26",
        "2026-10-27",
        "2026-10-28",
        "2026-10-29",
        "2026-10-30",
        "2026-10-31",
    }
    result = validator.evaluate_window(
        target_date="2026-10-31",
        window_spec=spec,
        available_partitions=partitions,
    )

    assert result.is_complete
    assert result.completeness_score == 1.0
    assert result.missing_intervals == []
    assert result.gating_action == "PROCEED_CLEAN"
    assert result.quality_markers["_dq_7d_revenue_complete"] is True
    assert result.quality_markers["_dq_7d_revenue_score"] == 1.0


def test_missing_day_in_seven_day_window_degraded_mode():
    """1 missing day out of 7 should produce completeness_score 0.8571 and quality markers."""
    spec = RollingWindowSpec(
        name="7d_revenue",
        window_size_days=7,
        metric_name="rolling_revenue_7d",
        aggregation_expr="sum(amount)",
    )
    validator = RollingWindowValidator(policy=GatingPolicy.DEGRADED_WITH_MARKER)

    # Missing 2026-10-28
    partitions = {
        "2026-10-25",
        "2026-10-26",
        "2026-10-27",
        # 2026-10-28 missing!
        "2026-10-29",
        "2026-10-30",
        "2026-10-31",
    }
    result = validator.evaluate_window(
        target_date="2026-10-31",
        window_spec=spec,
        available_partitions=partitions,
    )

    assert not result.is_complete
    assert result.completeness_score == round(6 / 7, 4)
    assert result.missing_intervals == ["2026-10-28"]
    assert result.gating_action == "PROCEED_WITH_QUALITY_MARKERS"
    assert result.quality_markers["_dq_7d_revenue_complete"] is False
    assert result.quality_markers["_dq_7d_revenue_score"] == round(6 / 7, 4)
    assert result.quality_markers["_dq_7d_revenue_missing_intervals"] == ["2026-10-28"]


def test_fail_fast_policy_raises_error():
    """FAIL_FAST policy must abort pipeline when window is incomplete."""
    spec = RollingWindowSpec(
        name="7d_revenue",
        window_size_days=7,
        metric_name="rolling_revenue_7d",
        aggregation_expr="sum(amount)",
    )
    validator = RollingWindowValidator(policy=GatingPolicy.FAIL_FAST)

    partitions = {"2026-10-30", "2026-10-31"}  # Missing 5 days

    with pytest.raises(IncompleteWindowError) as exc_info:
        validator.evaluate_window(
            target_date="2026-10-31",
            window_spec=spec,
            available_partitions=partitions,
        )

    assert "Rolling window '7d_revenue' for 2026-10-31 is incomplete!" in str(exc_info.value)
