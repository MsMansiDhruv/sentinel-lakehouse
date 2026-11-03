"""Telemetry models and incident definitions for Lakehouse pipeline failures."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any


class IncidentType(str, enum.Enum):
    """Categorized pipeline failure types."""

    SCHEMA_DRIFT = "schema_drift"
    SLA_BREACH = "sla_breach"
    NULL_VIOLATION = "null_violation"
    PARTITION_CONTIGUITY_GAP = "partition_contiguity_gap"
    SQL_SYNTAX_ERROR = "sql_syntax_error"
    DATA_QUALITY_ANOMALY = "data_quality_anomaly"


class IncidentSeverity(str, enum.Enum):
    """Severity levels for pipeline incidents."""

    P0_CRITICAL = "P0_CRITICAL"
    P1_HIGH = "P1_HIGH"
    P2_MEDIUM = "P2_MEDIUM"
    P3_LOW = "P3_LOW"


@dataclass
class PipelineIncident:
    """An incident triggered by Lakehouse pipeline monitors or quality gates."""

    incident_id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    target_table: str
    error_message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type.value,
            "severity": self.severity.value,
            "target_table": self.target_table,
            "error_message": self.error_message,
            "details": self.details,
            "timestamp": self.timestamp,
        }
