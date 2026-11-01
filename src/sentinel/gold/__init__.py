"""Sentinel Gold Quality Accelerator package."""

from sentinel.gold.accelerator import (
    GoldExecutionReport,
    SentinelGoldAccelerator,
)
from sentinel.gold.config import (
    GatingPolicy,
    GoldQualityContract,
    PartitionCadence,
    RollingWindowSpec,
    SlaStatus,
)
from sentinel.gold.ledger import QualityAuditEvent, QualityAuditLedger
from sentinel.gold.reconciler import BlastRadiusResult, RetroactiveReconciler
from sentinel.gold.sla_gate import DeltaMetadataSlaGate, SlaCheckResult
from sentinel.gold.window_validator import (
    IncompleteWindowError,
    RollingWindowValidator,
    WindowValidationResult,
)

__all__ = [
    "BlastRadiusResult",
    "DeltaMetadataSlaGate",
    "GatingPolicy",
    "GoldExecutionReport",
    "GoldQualityContract",
    "IncompleteWindowError",
    "PartitionCadence",
    "QualityAuditEvent",
    "QualityAuditLedger",
    "RetroactiveReconciler",
    "RollingWindowSpec",
    "RollingWindowValidator",
    "SentinelGoldAccelerator",
    "SlaCheckResult",
    "SlaStatus",
    "WindowValidationResult",
]
