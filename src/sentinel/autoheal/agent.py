"""Autonomous self-healing AI agent for Lakehouse pipelines and data engineering."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sentinel.autoheal.incident import IncidentSeverity, IncidentType, PipelineIncident
from sentinel.autoheal.tools import AutoHealToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class RemediationAction:
    """An individual actionable step within an auto-healing remediation plan."""

    action_type: str
    description: str
    target: str
    payload: dict[str, Any]
    reversible: bool = True


@dataclass
class RemediationPlan:
    """Structured remediation plan produced by AutoHealAgent."""

    incident_id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    root_cause: str
    confidence_score: float
    actions: list[RemediationAction] = field(default_factory=list)
    summary_markdown: str = ""
    is_automated_execution_safe: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type.value,
            "severity": self.severity.value,
            "root_cause": self.root_cause,
            "confidence_score": self.confidence_score,
            "actions": [
                {
                    "action_type": a.action_type,
                    "description": a.description,
                    "target": a.target,
                    "payload": a.payload,
                    "reversible": a.reversible,
                }
                for a in self.actions
            ],
            "summary_markdown": self.summary_markdown,
            "is_automated_execution_safe": self.is_automated_execution_safe,
        }


class AutoHealAgent:
    """Autonomous agent orchestrating diagnosis, AST patching, and Lakehouse self-healing."""

    def __init__(self, tools: AutoHealToolRegistry | None = None) -> None:
        self.tools = tools or AutoHealToolRegistry()

    def resolve_incident(self, incident: PipelineIncident) -> RemediationPlan:
        """Execute autonomous triage, root cause analysis, and remediation planning."""
        logger.info(
            "AutoHealAgent received incident %s (%s) for table %s",
            incident.incident_id,
            incident.incident_type.value,
            incident.target_table,
        )

        if incident.incident_type == IncidentType.SCHEMA_DRIFT:
            return self._handle_schema_drift(incident)
        elif incident.incident_type == IncidentType.NULL_VIOLATION:
            return self._handle_null_violation(incident)
        elif incident.incident_type in (
            IncidentType.PARTITION_CONTIGUITY_GAP,
            IncidentType.SLA_BREACH,
        ):
            return self._handle_partition_gap(incident)
        elif incident.incident_type == IncidentType.SQL_SYNTAX_ERROR:
            return self._handle_sql_syntax_error(incident)
        else:
            return self._handle_generic_anomaly(incident)

    def _handle_schema_drift(self, incident: PipelineIncident) -> RemediationPlan:
        expected = incident.details.get("expected_schema", {})
        actual = incident.details.get("actual_schema", {})
        drift = self.tools.detect_schema_drift(expected, actual)

        actions: list[RemediationAction] = []
        confidence = 0.95

        # Check column renaming or missing columns
        column_mapping = incident.details.get("column_mapping", {})
        if not column_mapping and drift.missing_columns and drift.unexpected_columns:
            # Automatic heuristic alias match if lengths match or names similar
            for m in drift.missing_columns:
                for u in drift.unexpected_columns:
                    if m.lower() in u.lower() or u.lower() in m.lower():
                        column_mapping[m] = u

        failing_sql = incident.details.get("failing_sql")
        if failing_sql and column_mapping:
            rewritten_sql = self.tools.parse_and_rewrite_sql(
                failing_sql, column_mapping
            )
            actions.append(
                RemediationAction(
                    action_type="rewrite_sql_ast",
                    description=f"Rewrote failing query AST using column mapping {column_mapping}",
                    target=incident.target_table,
                    payload={
                        "original_sql": failing_sql,
                        "repaired_sql": rewritten_sql,
                    },
                    reversible=True,
                )
            )

        if drift.unexpected_columns:
            actions.append(
                RemediationAction(
                    action_type="evolve_schema",
                    description=f"Alter table to add new columns: {drift.unexpected_columns}",
                    target=incident.target_table,
                    payload={"columns_to_add": drift.unexpected_columns},
                    reversible=False,
                )
            )

        summary = (
            f"### AutoHeal RCA: Schema Drift on `{incident.target_table}`\n\n"
            f"- **Missing Columns**: {drift.missing_columns}\n"
            f"- **Unexpected Columns**: {drift.unexpected_columns}\n"
            f"- **Type Mismatches**: {drift.type_mismatches}\n"
            f"- **Planned Actions**: {len(actions)} auto-remediation steps\n"
        )

        return RemediationPlan(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type,
            severity=incident.severity,
            root_cause=f"Schema drift detected: missing {drift.missing_columns}, unexpected {drift.unexpected_columns}",
            confidence_score=confidence,
            actions=actions,
            summary_markdown=summary,
            is_automated_execution_safe=incident.severity
            != IncidentSeverity.P0_CRITICAL,
        )

    def _handle_null_violation(self, incident: PipelineIncident) -> RemediationPlan:
        column = incident.details.get("column", "unknown_column")
        threshold = incident.details.get("threshold", 0.0)
        actual_ratio = incident.details.get("actual_null_ratio", 1.0)

        quarantine_rule = self.tools.generate_quarantine_rule(
            table_name=incident.target_table,
            rule_name=f"quarantine_null_{column}",
            condition=f"{column} IS NOT NULL",
        )

        actions = [
            RemediationAction(
                action_type="apply_quarantine_filter",
                description=f"Route rows where {column} IS NULL to quarantine table",
                target=incident.target_table,
                payload=quarantine_rule,
                reversible=True,
            )
        ]

        summary = (
            f"### AutoHeal RCA: Critical Null Violation on `{incident.target_table}`\n\n"
            f"- **Column**: `{column}`\n"
            f"- **Null Ratio**: {actual_ratio:.2%} (Threshold: {threshold:.2%})\n"
            f"- **Mitigation**: Divert invalid records to quarantine sink and unblock pipeline.\n"
        )

        return RemediationPlan(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type,
            severity=incident.severity,
            root_cause=f"Column '{column}' exceeded null threshold ({actual_ratio:.2%} > {threshold:.2%})",
            confidence_score=0.98,
            actions=actions,
            summary_markdown=summary,
            is_automated_execution_safe=True,
        )

    def _handle_partition_gap(self, incident: PipelineIncident) -> RemediationPlan:
        gap_date = incident.details.get("gap_date", "2026-11-01")
        window_size = incident.details.get("window_size_days", 1)

        merge_plan = self.tools.generate_reconciler_merge_plan(
            table_name=incident.target_table,
            t_late_str=gap_date,
            window_size_days=window_size,
        )

        actions = [
            RemediationAction(
                action_type="execute_delta_merge_restatement",
                description=f"Execute surgical Delta Lake MERGE for partitions {gap_date} (+{window_size}d)",
                target=incident.target_table,
                payload=merge_plan,
                reversible=True,
            )
        ]

        summary = (
            f"### AutoHeal RCA: Partition Contiguity Gap on `{incident.target_table}`\n\n"
            f"- **Missing Partition(s)**: {gap_date} to {merge_plan['blast_radius_end']}\n"
            f"- **Surgical Blast Radius**: {merge_plan['partition_pruning_clause']}\n"
            f"- **Action**: Restatement MERGE without table lock.\n"
        )

        return RemediationPlan(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type,
            severity=incident.severity,
            root_cause=f"Data pipeline missed partition interval starting {gap_date}",
            confidence_score=0.92,
            actions=actions,
            summary_markdown=summary,
            is_automated_execution_safe=True,
        )

    def _handle_sql_syntax_error(self, incident: PipelineIncident) -> RemediationPlan:
        sql = incident.details.get("sql", "")
        error_msg = incident.error_message
        mapping = incident.details.get("column_mapping", {})

        repaired_sql = (
            self.tools.parse_and_rewrite_sql(sql, mapping) if (sql and mapping) else sql
        )

        actions = [
            RemediationAction(
                action_type="rewrite_sql_ast",
                description="Parsed and rewrote SQL statement AST",
                target=incident.target_table,
                payload={"original_sql": sql, "repaired_sql": repaired_sql},
                reversible=True,
            )
        ]

        return RemediationPlan(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type,
            severity=incident.severity,
            root_cause=f"SQL syntax or column resolution failure: {error_msg}",
            confidence_score=0.88,
            actions=actions,
            summary_markdown=f"### AutoHeal RCA: SQL AST Repair\n\n```sql\n{repaired_sql}\n```\n",
            is_automated_execution_safe=True,
        )

    def _handle_generic_anomaly(self, incident: PipelineIncident) -> RemediationPlan:
        commits = self.tools.inspect_delta_commit_log(incident.target_table)
        summary = (
            f"### AutoHeal RCA: Anomaly Investigation on `{incident.target_table}`\n\n"
            f"- Error: {incident.error_message}\n"
            f"- Recent commits checked: {len(commits)}\n"
        )
        return RemediationPlan(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type,
            severity=incident.severity,
            root_cause=f"Anomaly detected in table {incident.target_table}: {incident.error_message}",
            confidence_score=0.75,
            actions=[],
            summary_markdown=summary,
            is_automated_execution_safe=False,
        )
