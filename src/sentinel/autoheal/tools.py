"""Deterministic tools invoked by the AutoHeal-DE autonomous agent."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp


@dataclass
class SchemaDriftResult:
    """Detected schema discrepancy between expected contract and actual data."""

    has_drift: bool
    missing_columns: list[str] = field(default_factory=list)
    unexpected_columns: list[str] = field(default_factory=list)
    type_mismatches: dict[str, tuple[str, str]] = field(default_factory=dict)


@dataclass
class DeltaCommitSummary:
    """Summarized action from Delta Lake transaction log."""

    version: int
    operation: str
    timestamp: str
    num_added_files: int
    num_removed_files: int
    schema_changed: bool


class AutoHealToolRegistry:
    """Registry of deterministic tools accessible to the autonomous healing agent."""

    def __init__(self) -> None:
        pass

    def inspect_delta_commit_log(
        self,
        table_name: str,
        mock_history: list[dict[str, Any]] | None = None,
    ) -> list[DeltaCommitSummary]:
        """Inspect recent Delta Lake commit log entries for schema changes or anomalous file writes."""
        history = mock_history or [
            {
                "version": 42,
                "operation": "WRITE",
                "timestamp": "2026-11-03T10:00:00Z",
                "num_added_files": 12,
                "num_removed_files": 0,
                "schema_changed": False,
            },
            {
                "version": 41,
                "operation": "MERGE",
                "timestamp": "2026-11-02T22:30:00Z",
                "num_added_files": 4,
                "num_removed_files": 4,
                "schema_changed": True,
            },
        ]
        return [
            DeltaCommitSummary(
                version=h["version"],
                operation=h["operation"],
                timestamp=h["timestamp"],
                num_added_files=h["num_added_files"],
                num_removed_files=h["num_removed_files"],
                schema_changed=h.get("schema_changed", False),
            )
            for h in history
        ]

    def detect_schema_drift(
        self,
        expected_schema: dict[str, str],
        actual_schema: dict[str, str],
    ) -> SchemaDriftResult:
        """Compare expected schema definition against actual incoming DataFrame schema."""
        missing = [col for col in expected_schema if col not in actual_schema]
        unexpected = [col for col in actual_schema if col not in expected_schema]
        mismatches: dict[str, tuple[str, str]] = {}

        for col, exp_type in expected_schema.items():
            if col in actual_schema:
                act_type = actual_schema[col]
                if exp_type.lower() != act_type.lower():
                    mismatches[col] = (exp_type, act_type)

        has_drift = bool(missing or unexpected or mismatches)
        return SchemaDriftResult(
            has_drift=has_drift,
            missing_columns=missing,
            unexpected_columns=unexpected,
            type_mismatches=mismatches,
        )

    def parse_and_rewrite_sql(
        self,
        sql_query: str,
        column_mapping: dict[str, str],
    ) -> str:
        """Use SQLGlot AST parser to safely rewrite column identifiers and repair query syntax."""
        expression = sqlglot.parse_one(sql_query, read="spark")

        def transformer(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Column):
                col_name = node.name
                if col_name in column_mapping:
                    return exp.column(column_mapping[col_name], table=node.table)
            return node

        rewritten = expression.transform(transformer)
        return rewritten.sql(dialect="spark")

    def generate_quarantine_rule(
        self,
        table_name: str,
        rule_name: str,
        condition: str,
    ) -> dict[str, Any]:
        """Generate a Lakeflow / Great Expectations quarantine filter specification."""
        return {
            "target_table": table_name,
            "rule_name": rule_name,
            "expectation": "expect_column_values_to_not_be_null",
            "filter_sql": condition,
            "routing": {
                "valid_destination": f"{table_name}_clean",
                "quarantine_destination": f"{table_name}_quarantine",
                "tag_failed_record": True,
            },
        }

    def generate_reconciler_merge_plan(
        self,
        table_name: str,
        t_late_str: str,
        window_size_days: int,
    ) -> dict[str, Any]:
        """Compute the surgical blast-radius partition range and generate a Delta MERGE restatement script."""
        t_late = datetime.date.fromisoformat(t_late_str)
        t_end = t_late + datetime.timedelta(days=window_size_days - 1)

        merge_sql = (
            f"MERGE INTO {table_name} AS target "  # nosec B608
            f"USING source_reconciled AS source "
            f"ON target.partition_date = source.partition_date AND target.id = source.id "
            f"AND target.partition_date BETWEEN '{t_late.isoformat()}' AND '{t_end.isoformat()}' "
            f"WHEN MATCHED THEN UPDATE SET * "
            f"WHEN NOT MATCHED THEN INSERT *;"
        )

        return {
            "target_table": table_name,
            "t_late": t_late.isoformat(),
            "window_size_days": window_size_days,
            "blast_radius_start": t_late.isoformat(),
            "blast_radius_end": t_end.isoformat(),
            "delta_merge_sql": merge_sql,
            "partition_pruning_clause": f"partition_date BETWEEN '{t_late.isoformat()}' AND '{t_end.isoformat()}'",
        }
