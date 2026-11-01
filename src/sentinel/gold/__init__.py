"""Sentinel Gold Quality Accelerator package."""

from sentinel.gold.accelerator import (
    GoldExecutionReport,
    SentinelGoldAccelerator,
)
from sentinel.gold.alerts import (
    AlertDispatcher,
    AlertSeverity,
    IncidentRecord,
    IncidentState,
)
from sentinel.gold.config import (
    GatingPolicy,
    GoldQualityContract,
    PartitionCadence,
    RollingWindowSpec,
    SlaStatus,
)
from sentinel.gold.contract import (
    ContractParsingError,
    SentinelContractParser,
)
from sentinel.gold.ledger import QualityAuditEvent, QualityAuditLedger
from sentinel.gold.profiler import (
    DeltaMetadataProfiler,
    FileHealthReport,
    MetadataProfileReport,
    VolumeAnomalyResult,
)
from sentinel.gold.reconciler import BlastRadiusResult, RetroactiveReconciler
from sentinel.gold.sla_gate import DeltaMetadataSlaGate, SlaCheckResult
from sentinel.gold.window_validator import (
    IncompleteWindowError,
    RollingWindowValidator,
    WindowValidationResult,
)

__all__ = [
    "AlertDispatcher",
    "AlertSeverity",
    "BlastRadiusResult",
    "ContractParsingError",
    "DeltaMetadataProfiler",
    "DeltaMetadataSlaGate",
    "FileHealthReport",
    "GatingPolicy",
    "GoldExecutionReport",
    "GoldQualityContract",
    "IncidentRecord",
    "IncidentState",
    "IncompleteWindowError",
    "MetadataProfileReport",
    "PartitionCadence",
    "QualityAuditEvent",
    "QualityAuditLedger",
    "RetroactiveReconciler",
    "RollingWindowSpec",
    "RollingWindowValidator",
    "SentinelContractParser",
    "SentinelGoldAccelerator",
    "SlaCheckResult",
    "SlaStatus",
    "VolumeAnomalyResult",
    "WindowValidationResult",
]
