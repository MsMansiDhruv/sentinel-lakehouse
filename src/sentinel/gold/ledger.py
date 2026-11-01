"""Audit ledger for recording Gold quality evaluations, SLA events, and reconciliations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class QualityAuditEvent:
    """Individual audit record for a Gold pipeline execution."""

    event_id: str
    target_table: str
    target_date: str
    event_type: str  # 'SLA_EVALUATION', 'WINDOW_COMPLETENESS', 'RETROACTIVE_RECONCILIATION'
    status: str
    completeness_score: float
    is_breached: bool
    missing_intervals: List[str]
    affected_windows: List[str]
    scan_reduction_pct: float
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_row(self) -> Dict[str, Any]:
        """Convert event to a dictionary row suitable for Delta Lake append."""
        row = asdict(self)
        row["timestamp"] = self.timestamp.isoformat()
        return row


class QualityAuditLedger:
    """Maintains an audit trail of Gold data quality checks and DBU optimizations.

    Provides governance observability in Unity Catalog under `_sentinel_gold_quality_ledger`.
    """

    def __init__(self, target_table: str):
        self.target_table = target_table
        self.events: List[QualityAuditEvent] = []

    def record_sla_check(
        self,
        target_date: str,
        status: str,
        is_breached: bool,
        missing_partitions: List[str],
        dbu_savings_pct: float = 99.9,
        details: Optional[Dict[str, Any]] = None,
    ) -> QualityAuditEvent:
        """Record a partition arrival SLA evaluation event."""
        event = QualityAuditEvent(
            event_id=str(uuid.uuid4()),
            target_table=self.target_table,
            target_date=target_date,
            event_type="SLA_EVALUATION",
            status=status,
            completeness_score=0.0 if missing_partitions else 1.0,
            is_breached=is_breached,
            missing_intervals=missing_partitions,
            affected_windows=[target_date],
            scan_reduction_pct=dbu_savings_pct,
            details=details or {},
        )
        self.events.append(event)
        return event

    def record_window_validation(
        self,
        target_date: str,
        window_name: str,
        completeness_score: float,
        is_complete: bool,
        missing_intervals: List[str],
        details: Optional[Dict[str, Any]] = None,
    ) -> QualityAuditEvent:
        """Record a rolling window completeness check."""
        event = QualityAuditEvent(
            event_id=str(uuid.uuid4()),
            target_table=self.target_table,
            target_date=target_date,
            event_type="WINDOW_COMPLETENESS",
            status="COMPLETE" if is_complete else "DEGRADED",
            completeness_score=completeness_score,
            is_breached=not is_complete,
            missing_intervals=missing_intervals,
            affected_windows=[window_name],
            scan_reduction_pct=100.0,
            details=details or {},
        )
        self.events.append(event)
        return event

    def record_reconciliation(
        self,
        target_date: str,
        invalidated_dates: List[str],
        scan_reduction_pct: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> QualityAuditEvent:
        """Record an automated blast-radius reconciliation event."""
        event = QualityAuditEvent(
            event_id=str(uuid.uuid4()),
            target_table=self.target_table,
            target_date=target_date,
            event_type="RETROACTIVE_RECONCILIATION",
            status="RECONCILED",
            completeness_score=1.0,
            is_breached=False,
            missing_intervals=[],
            affected_windows=invalidated_dates,
            scan_reduction_pct=scan_reduction_pct,
            details=details or {},
        )
        self.events.append(event)
        return event

    def get_summary(self) -> Dict[str, Any]:
        """Generate high-level quality & efficiency summary."""
        if not self.events:
            return {"total_events": 0, "status": "NO_ACTIVITY"}

        sla_events = [e for e in self.events if e.event_type == "SLA_EVALUATION"]
        window_events = [e for e in self.events if e.event_type == "WINDOW_COMPLETENESS"]
        recon_events = [
            e for e in self.events if e.event_type == "RETROACTIVE_RECONCILIATION"
        ]

        avg_score = (
            sum(e.completeness_score for e in window_events) / len(window_events)
            if window_events
            else 1.0
        )
        avg_scan_red = (
            sum(e.scan_reduction_pct for e in self.events) / len(self.events)
            if self.events
            else 0.0
        )

        return {
            "total_events": len(self.events),
            "sla_evaluations": len(sla_events),
            "window_evaluations": len(window_events),
            "reconciliations_triggered": len(recon_events),
            "average_completeness_score": round(avg_score, 4),
            "average_scan_reduction_pct": round(avg_scan_red, 2),
            "total_breaches": sum(1 for e in self.events if e.is_breached),
        }
