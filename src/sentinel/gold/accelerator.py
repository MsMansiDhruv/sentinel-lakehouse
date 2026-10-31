"""Sentinel Gold Quality Accelerator: Enterprise Databricks rolling-window quality engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Set

from sentinel.gold.config import (
    GatingPolicy,
    GoldQualityContract,
    RollingWindowSpec,
)
from sentinel.gold.ledger import QualityAuditLedger
from sentinel.gold.reconciler import BlastRadiusResult, RetroactiveReconciler
from sentinel.gold.sla_gate import DeltaMetadataSlaGate, SlaCheckResult
from sentinel.gold.window_validator import (
    RollingWindowValidator,
    WindowValidationResult,
)


@dataclass
class GoldExecutionReport:
    """Consolidated execution output for Gold pipeline runs."""

    target_date: str
    sla_result: SlaCheckResult
    window_results: Dict[str, WindowValidationResult]
    quality_markers: Dict[str, Any]
    can_proceed: bool
    reconciliation_plan: Optional[BlastRadiusResult] = None
    delta_merge_sql: Optional[str] = None
    summary_message: str = ""


class SentinelGoldAccelerator:
    """The unified Gold Quality Accelerator engine.

    A custom, zero-overhead alternative to expensive Databricks Marketplace tools
    and heavy Lakehouse Monitoring monitors.
    """

    def __init__(self, contract: GoldQualityContract):
        self.contract = contract
        self.sla_gate = DeltaMetadataSlaGate(contract)
        self.window_validator = RollingWindowValidator(contract.gating_policy)
        self.reconciler = RetroactiveReconciler(contract)
        self.ledger = QualityAuditLedger(contract.target_table)

    def run_pipeline_check(
        self,
        target_date: str | date,
        available_partitions: Set[str] | List[str],
        late_partitions: Optional[List[str]] = None,
        partition_row_counts: Optional[Dict[str, int]] = None,
    ) -> GoldExecutionReport:
        """Run complete Gold data quality pre-flight and reconciliation checks.

        Args:
            target_date: Target calculation date.
            available_partitions: Partitions discovered via Delta transaction log.
            late_partitions: Any newly arrived partitions for past dates.
            partition_row_counts: Optional row counts from Delta file statistics.
        """
        target_str = str(target_date)

        # 1. Zero-scan Delta Metadata SLA Gate
        sla_res = self.sla_gate.evaluate_arrival(
            target_date=target_str,
            available_partitions=available_partitions,
            partition_row_counts=partition_row_counts,
        )
        self.ledger.record_sla_check(
            target_date=target_str,
            status=sla_res.status.value,
            is_breached=sla_res.is_breached,
            missing_partitions=sla_res.missing_partitions,
            dbu_savings_pct=sla_res.dbu_savings_pct,
            details=sla_res.details,
        )

        # 2. Evaluate Rolling Windows Contiguity
        window_results: Dict[str, WindowValidationResult] = {}
        merged_quality_markers: Dict[str, Any] = {}
        all_windows_valid = True

        for spec in self.contract.rolling_windows:
            w_res = self.window_validator.evaluate_window(
                target_date=target_str,
                window_spec=spec,
                available_partitions=available_partitions,
                raise_on_failure=False,
            )
            window_results[spec.name] = w_res
            merged_quality_markers.update(w_res.quality_markers)
            if not w_res.is_complete:
                all_windows_valid = False

            self.ledger.record_window_validation(
                target_date=target_str,
                window_name=spec.name,
                completeness_score=w_res.completeness_score,
                is_complete=w_res.is_complete,
                missing_intervals=w_res.missing_intervals,
            )

        # 3. Check for Late-Arriving Partitions & Blast Radius
        recon_plan: Optional[BlastRadiusResult] = None
        merge_sql: Optional[str] = None

        if late_partitions:
            recon_plan = self.reconciler.calculate_blast_radius(
                late_partitions=late_partitions,
                as_of_date=target_str,
            )
            if recon_plan.invalidated_target_dates:
                merge_sql = self.reconciler.generate_delta_merge_sql(recon_plan)
                self.ledger.record_reconciliation(
                    target_date=target_str,
                    invalidated_dates=recon_plan.invalidated_target_dates,
                    scan_reduction_pct=recon_plan.scan_reduction_pct,
                    details=recon_plan.details,
                )

        # Determine if execution can proceed
        can_proceed = True
        summary_msg = "Gold pipeline quality verified cleanly."

        if sla_res.is_breached or not all_windows_valid:
            if self.contract.gating_policy == GatingPolicy.FAIL_FAST:
                can_proceed = False
                summary_msg = (
                    "Execution halted due to FAIL_FAST policy on SLA or window breach."
                )
            elif self.contract.gating_policy == GatingPolicy.DEGRADED_WITH_MARKER:
                can_proceed = True
                summary_msg = (
                    "Proceeding in DEGRADED mode with injected quality markers."
                )
            elif self.contract.gating_policy == GatingPolicy.QUARANTINE_WINDOW:
                can_proceed = True
                summary_msg = "Proceeding with incomplete window routed to quarantine."

        return GoldExecutionReport(
            target_date=target_str,
            sla_result=sla_res,
            window_results=window_results,
            quality_markers=merged_quality_markers,
            can_proceed=can_proceed,
            reconciliation_plan=recon_plan,
            delta_merge_sql=merge_sql,
            summary_message=summary_msg,
        )
