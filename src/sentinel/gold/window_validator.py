"""Contiguity and completeness validation for rolling windows at the Gold layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sentinel.gold.config import GatingPolicy, RollingWindowSpec


class IncompleteWindowError(Exception):
    """Raised when a rolling window fails completeness requirements under FAIL_FAST."""

    pass


@dataclass
class WindowValidationResult:
    """Result of checking a rolling window for interval completeness."""

    window_name: str
    target_date: str
    window_size_days: int
    expected_intervals: List[str]
    present_intervals: List[str]
    missing_intervals: List[str]
    completeness_score: float
    is_complete: bool
    gating_action: str
    quality_markers: Dict[str, Any] = field(default_factory=dict)


class RollingWindowValidator:
    """Validates the contiguity of rolling windows to prevent publishing corrupted aggregates.

    In Medallion architectures, rolling window metrics (e.g. 7-day revenue, 30-day active users)
    depend on a contiguous historical interval. If one day in the window is missing or delayed,
    standard jobs compute partial aggregations with missing denominators.
    This validator detects gaps, calculates completeness ratios, and annotates Gold records
    with non-breaking quality markers.
    """

    def __init__(self, policy: GatingPolicy = GatingPolicy.DEGRADED_WITH_MARKER):
        self.policy = policy

    def evaluate_window(
        self,
        target_date: str | date,
        window_spec: RollingWindowSpec,
        available_partitions: Set[str] | List[str],
        raise_on_failure: bool = False,
    ) -> WindowValidationResult:
        """Evaluate a rolling window interval for contiguity.

        Args:
            target_date: Target calculation date (e.g., '2026-10-31').
            window_spec: RollingWindowSpec defining window size and metric rules.
            available_partitions: Set of available partition dates in Silver/source.
            raise_on_failure: Whether to immediately raise IncompleteWindowError on FAIL_FAST.
        """
        target_str = str(target_date)
        present_set = set(str(p) for p in available_partitions)

        target_dt = datetime.strptime(target_str, "%Y-%m-%d").date()
        w_size = window_spec.window_size_days

        # Generate expected contiguous date range: [target_dt - (w_size - 1), target_dt]
        expected_intervals = [
            (target_dt - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in reversed(range(w_size))
        ]

        present_intervals = [d for d in expected_intervals if d in present_set]
        missing_intervals = [d for d in expected_intervals if d not in present_set]

        completeness_score = (
            len(present_intervals) / len(expected_intervals)
            if expected_intervals
            else 1.0
        )
        is_complete = completeness_score >= window_spec.min_completeness_ratio

        quality_markers = {
            f"_dq_{window_spec.name}_complete": is_complete,
            f"_dq_{window_spec.name}_score": round(completeness_score, 4),
            f"_dq_{window_spec.name}_missing_count": len(missing_intervals),
            f"_dq_{window_spec.name}_missing_intervals": missing_intervals,
        }

        # Determine gating action
        if is_complete:
            gating_action = "PROCEED_CLEAN"
        elif self.policy == GatingPolicy.FAIL_FAST:
            gating_action = "FAIL_FAST_ABORT"
            if raise_on_failure:
                raise IncompleteWindowError(
                    f"Rolling window '{window_spec.name}' for {target_str} is incomplete! "
                    f"Completeness score: {completeness_score:.2f} < {window_spec.min_completeness_ratio:.2f}. "
                    f"Missing intervals: {missing_intervals}"
                )
        elif self.policy == GatingPolicy.QUARANTINE_WINDOW:
            gating_action = "ROUTE_TO_QUARANTINE"
        elif self.policy == GatingPolicy.DEGRADED_WITH_MARKER:
            gating_action = "PROCEED_WITH_QUALITY_MARKERS"
        else:
            gating_action = "PROCEED_WITH_WARNING"

        return WindowValidationResult(
            window_name=window_spec.name,
            target_date=target_str,
            window_size_days=w_size,
            expected_intervals=expected_intervals,
            present_intervals=present_intervals,
            missing_intervals=missing_intervals,
            completeness_score=round(completeness_score, 4),
            is_complete=is_complete,
            gating_action=gating_action,
            quality_markers=quality_markers,
        )
