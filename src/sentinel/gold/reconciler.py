"""Retroactive blast-radius reconciliation for late-arriving data in rolling windows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sentinel.gold.config import GoldQualityContract


@dataclass
class BlastRadiusResult:
    """The calculated impact radius of late-arriving partitions on Gold windows."""

    late_partitions: List[str]
    max_window_days: int
    invalidated_target_dates: List[str]
    source_required_start_date: str
    source_required_end_date: str
    target_merge_predicate: str
    estimated_full_table_scan_days: int
    actual_pruned_scan_days: int
    scan_reduction_pct: float
    details: Dict[str, Any] = field(default_factory=dict)


class RetroactiveReconciler:
    """Calculates late data blast radius and orchestrates Delta reconciliations.

    Unlike expensive third-party tools that merely sound an alert and force engineers
    to run costly full-table backfills, the RetroactiveReconciler:
    1. Identifies which historical rolling windows were invalidated by late data.
    2. Bounds the blast radius to strictly [t_late, t_late + W - 1].
    3. Produces partition-pruned Delta MERGE statements skipping 95-99% of data.
    """

    def __init__(self, contract: GoldQualityContract):
        self.contract = contract

    def calculate_blast_radius(
        self,
        late_partitions: List[str],
        as_of_date: Optional[str | date] = None,
        full_table_retention_days: int = 365,
    ) -> BlastRadiusResult:
        """Compute the invalidated target dates and Delta MERGE boundary.

        Args:
            late_partitions: Partition date strings 'YYYY-MM-DD' that arrived late.
            as_of_date: Current date boundary beyond which dates are not recomputed.
            full_table_retention_days: Baseline retention days for scan reduction.
        """
        if not late_partitions:
            return BlastRadiusResult(
                late_partitions=[],
                max_window_days=0,
                invalidated_target_dates=[],
                source_required_start_date="",
                source_required_end_date="",
                target_merge_predicate="1 = 0",
                estimated_full_table_scan_days=full_table_retention_days,
                actual_pruned_scan_days=0,
                scan_reduction_pct=100.0,
                details={"message": "No late partitions detected; zero backfill needed."},
            )

        as_of_dt = (
            datetime.strptime(str(as_of_date), "%Y-%m-%d").date()
            if as_of_date
            else date.today()
        )

        # Determine the maximum rolling window size
        max_w = max(
            (spec.window_size_days for spec in self.contract.rolling_windows),
            default=7,
        )

        invalidated_dates_set: Set[date] = set()
        late_dts = [datetime.strptime(p, "%Y-%m-%d").date() for p in late_partitions]

        for p_dt in late_dts:
            # A late partition p_dt invalidates target windows [p_dt, p_dt + max_w - 1]
            for offset in range(max_w):
                target_cand = p_dt + timedelta(days=offset)
                if target_cand <= as_of_dt:
                    invalidated_dates_set.add(target_cand)

        sorted_invalidated = sorted(invalidated_dates_set)
        invalidated_strs = [d.strftime("%Y-%m-%d") for d in sorted_invalidated]

        if not sorted_invalidated:
            return BlastRadiusResult(
                late_partitions=late_partitions,
                max_window_days=max_w,
                invalidated_target_dates=[],
                source_required_start_date="",
                source_required_end_date="",
                target_merge_predicate="1 = 0",
                estimated_full_table_scan_days=full_table_retention_days,
                actual_pruned_scan_days=0,
                scan_reduction_pct=100.0,
                details={"message": "Late partitions are beyond the as-of date."},
            )

        # Source data required: earliest invalidated date minus max_w days
        source_start_dt = sorted_invalidated[0] - timedelta(days=max_w - 1)
        source_end_dt = sorted_invalidated[-1]

        source_start_str = source_start_dt.strftime("%Y-%m-%d")
        source_end_str = source_end_dt.strftime("%Y-%m-%d")

        # Construct optimized Delta MERGE predicate
        if len(invalidated_strs) == 1:
            merge_pred = f"target.{self.contract.partition_column} = '{invalidated_strs[0]}'"
        else:
            merge_pred = (
                f"target.{self.contract.partition_column} >= '{invalidated_strs[0]}' "
                f"AND target.{self.contract.partition_column} <= '{invalidated_strs[-1]}'"
            )

        pruned_days = len(invalidated_strs)
        scan_reduction = round(
            ((full_table_retention_days - pruned_days) / full_table_retention_days) * 100.0,
            2,
        )

        return BlastRadiusResult(
            late_partitions=late_partitions,
            max_window_days=max_w,
            invalidated_target_dates=invalidated_strs,
            source_required_start_date=source_start_str,
            source_required_end_date=source_end_str,
            target_merge_predicate=merge_pred,
            estimated_full_table_scan_days=full_table_retention_days,
            actual_pruned_scan_days=pruned_days,
            scan_reduction_pct=max(0.0, scan_reduction),
            details={
                "target_table": self.contract.target_table,
                "earliest_late_partition": min(late_partitions),
                "latest_late_partition": max(late_partitions),
                "impacted_window_count": len(invalidated_strs),
            },
        )

    def generate_delta_merge_sql(
        self,
        blast_radius: BlastRadiusResult,
        source_view_name: str = "recomputed_staged_slice",
    ) -> str:
        """Generate partition-pruned Delta MERGE statement for reconciliation."""
        target_tbl = self.contract.target_table
        part_pred = blast_radius.target_merge_predicate

        join_conditions = [part_pred]
        for key in self.contract.primary_keys:
            join_conditions.append(f"target.{key} = source.{key}")

        on_clause = "\n   AND ".join(join_conditions)

        return f"""-- Sentinel Gold Automated Blast-Radius Reconciliation MERGE
-- Optimized partition pruning: scanning {blast_radius.actual_pruned_scan_days} days
-- Scan cost reduction: {blast_radius.scan_reduction_pct}%
MERGE INTO {target_tbl} AS target
USING {source_view_name} AS source
ON {on_clause}
WHEN MATCHED THEN
  UPDATE SET *
WHEN NOT MATCHED THEN
  INSERT *;
"""
