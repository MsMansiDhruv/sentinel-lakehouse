"""Tests for AutoHeal-DE deterministic tools."""

from sentinel.autoheal.tools import AutoHealToolRegistry


def test_detect_schema_drift_clean() -> None:
    tools = AutoHealToolRegistry()
    expected = {"id": "string", "amount": "double", "date": "date"}
    actual = {"id": "string", "amount": "double", "date": "date"}
    result = tools.detect_schema_drift(expected, actual)
    assert not result.has_drift
    assert result.missing_columns == []
    assert result.unexpected_columns == []
    assert result.type_mismatches == {}


def test_detect_schema_drift_mismatch_and_missing() -> None:
    tools = AutoHealToolRegistry()
    expected = {"id": "string", "total_val": "double", "status": "string"}
    actual = {"id": "string", "total_val": "int", "extra_col": "string"}
    result = tools.detect_schema_drift(expected, actual)
    assert result.has_drift
    assert result.missing_columns == ["status"]
    assert result.unexpected_columns == ["extra_col"]
    assert result.type_mismatches == {"total_val": ("double", "int")}


def test_parse_and_rewrite_sql_columns() -> None:
    tools = AutoHealToolRegistry()
    sql = "SELECT legacy_amount, user_id FROM sales WHERE legacy_amount > 100"
    mapping = {"legacy_amount": "net_amount"}
    rewritten = tools.parse_and_rewrite_sql(sql, mapping)
    assert "net_amount" in rewritten
    assert "legacy_amount" not in rewritten


def test_generate_quarantine_rule() -> None:
    tools = AutoHealToolRegistry()
    rule = tools.generate_quarantine_rule(
        "gold.transactions", "check_null_user", "user_id IS NOT NULL"
    )
    assert rule["target_table"] == "gold.transactions"
    assert rule["filter_sql"] == "user_id IS NOT NULL"
    assert rule["routing"]["quarantine_destination"] == "gold.transactions_quarantine"


def test_generate_reconciler_merge_plan() -> None:
    tools = AutoHealToolRegistry()
    plan = tools.generate_reconciler_merge_plan("gold.daily_metrics", "2026-11-01", 3)
    assert plan["target_table"] == "gold.daily_metrics"
    assert plan["blast_radius_start"] == "2026-11-01"
    assert plan["blast_radius_end"] == "2026-11-03"
    assert "MERGE INTO gold.daily_metrics" in plan["delta_merge_sql"]
    assert "BETWEEN '2026-11-01' AND '2026-11-03'" in plan["delta_merge_sql"]


def test_inspect_delta_commit_log() -> None:
    tools = AutoHealToolRegistry()
    commits = tools.inspect_delta_commit_log("gold.daily_metrics")
    assert len(commits) == 2
    assert commits[0].version == 42
    assert commits[1].operation == "MERGE"
