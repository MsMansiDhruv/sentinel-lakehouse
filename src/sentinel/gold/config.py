"""Configuration and contract dataclasses for the Sentinel Gold Quality Accelerator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List


class GatingPolicy(str, Enum):
    """Execution policy when upstream data arrival or window completeness fails."""

    # Abort pipeline execution to prevent publishing corrupted metrics
    FAIL_FAST = "FAIL_FAST"
    # Proceed, but annotate data with DQ confidence flags
    DEGRADED_WITH_MARKER = "DEGRADED_WITH_MARKER"
    # Route incomplete window rows to a quarantine table
    QUARANTINE_WINDOW = "QUARANTINE_WINDOW"
    # Log warning to audit ledger and proceed
    PROCEED_WITH_WARNING = "PROCEED_WITH_WARNING"


class SlaStatus(str, Enum):
    """Partition arrival SLA status."""

    ON_TIME = "ON_TIME"
    LATE_ARRIVING = "LATE_ARRIVING"
    SLA_BREACHED = "SLA_BREACHED"
    VOLUME_ANOMALY = "VOLUME_ANOMALY"
    HEALTHY = "HEALTHY"


class PartitionCadence(str, Enum):
    """Cadence of incoming partitions."""

    DAILY = "DAILY"
    HOURLY = "HOURLY"


@dataclass(frozen=True)
class RollingWindowSpec:
    """Specification for a rolling window metric at the Gold layer."""

    name: str
    window_size_days: int
    metric_name: str
    aggregation_expr: str
    time_column: str = "order_date"
    partition_column: str = "order_date"
    min_completeness_ratio: float = 1.0


@dataclass
class GoldQualityContract:
    """Declarative contract defining quality SLAs and rolling window requirements."""

    target_table: str
    source_table: str
    time_column: str = "order_date"
    partition_column: str = "order_date"
    primary_keys: List[str] = field(default_factory=lambda: ["order_date"])
    cadence: PartitionCadence = PartitionCadence.DAILY
    sla_grace_period_hours: int = 4
    min_expected_rows: int = 1
    gating_policy: GatingPolicy = GatingPolicy.DEGRADED_WITH_MARKER
    rolling_windows: List[RollingWindowSpec] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
