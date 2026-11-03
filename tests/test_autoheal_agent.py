"""Tests for AutoHeal-DE autonomous agent triage and remediation."""

from sentinel.autoheal.agent import AutoHealAgent
from sentinel.autoheal.incident import IncidentSeverity, IncidentType, PipelineIncident


def test_agent_resolves_schema_drift() -> None:
    agent = AutoHealAgent()
    incident = PipelineIncident(
        incident_id="INC-101",
        incident_type=IncidentType.SCHEMA_DRIFT,
        severity=IncidentSeverity.P1_HIGH,
        target_table="gold.sales_summary",
        error_message="Column 'legacy_amt' not found in source stream",
        details={
            "expected_schema": {"id": "string", "legacy_amt": "double"},
            "actual_schema": {"id": "string", "new_amt": "double"},
            "column_mapping": {"legacy_amt": "new_amt"},
            "failing_sql": "SELECT id, legacy_amt FROM gold.sales_summary",
        },
    )

    plan = agent.resolve_incident(incident)
    assert plan.incident_id == "INC-101"
    assert plan.confidence_score >= 0.90
    assert len(plan.actions) >= 1

    ast_action = next(a for a in plan.actions if a.action_type == "rewrite_sql_ast")
    assert "new_amt" in ast_action.payload["repaired_sql"]


def test_agent_resolves_null_violation() -> None:
    agent = AutoHealAgent()
    incident = PipelineIncident(
        incident_id="INC-102",
        incident_type=IncidentType.NULL_VIOLATION,
        severity=IncidentSeverity.P2_MEDIUM,
        target_table="gold.customer_dim",
        error_message="Null ratio exceeded for column email",
        details={
            "column": "email",
            "threshold": 0.01,
            "actual_null_ratio": 0.054,
        },
    )

    plan = agent.resolve_incident(incident)
    assert plan.is_automated_execution_safe is True
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.action_type == "apply_quarantine_filter"
    assert action.payload["filter_sql"] == "email IS NOT NULL"


def test_agent_resolves_partition_gap() -> None:
    agent = AutoHealAgent()
    incident = PipelineIncident(
        incident_id="INC-103",
        incident_type=IncidentType.PARTITION_CONTIGUITY_GAP,
        severity=IncidentSeverity.P1_HIGH,
        target_table="gold.orders",
        error_message="Missing partition contiguous interval",
        details={
            "gap_date": "2026-10-30",
            "window_size_days": 2,
        },
    )

    plan = agent.resolve_incident(incident)
    assert plan.confidence_score >= 0.90
    action = plan.actions[0]
    assert action.action_type == "execute_delta_merge_restatement"
    assert action.payload["blast_radius_start"] == "2026-10-30"
    assert action.payload["blast_radius_end"] == "2026-10-31"


def test_agent_resolves_sql_syntax_error() -> None:
    agent = AutoHealAgent()
    incident = PipelineIncident(
        incident_id="INC-104",
        incident_type=IncidentType.SQL_SYNTAX_ERROR,
        severity=IncidentSeverity.P2_MEDIUM,
        target_table="gold.invoices",
        error_message="Column 'old_ref' not resolved",
        details={
            "sql": "SELECT old_ref FROM gold.invoices",
            "column_mapping": {"old_ref": "ref_num"},
        },
    )

    plan = agent.resolve_incident(incident)
    assert len(plan.actions) == 1
    assert "ref_num" in plan.actions[0].payload["repaired_sql"]


def test_agent_resolves_generic_anomaly() -> None:
    agent = AutoHealAgent()
    incident = PipelineIncident(
        incident_id="INC-105",
        incident_type=IncidentType.DATA_QUALITY_ANOMALY,
        severity=IncidentSeverity.P0_CRITICAL,
        target_table="gold.transactions",
        error_message="Distribution spike in outlier transactions",
        details={},
    )

    plan = agent.resolve_incident(incident)
    # P0 critical anomalies should require human review
    assert plan.is_automated_execution_safe is False
