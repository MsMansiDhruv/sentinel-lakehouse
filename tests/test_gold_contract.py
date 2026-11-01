"""Unit tests for SentinelContractParser and plug-and-play declarative contracts."""

import pytest

from sentinel.gold.config import GatingPolicy, PartitionCadence
from sentinel.gold.contract import (
    ContractParsingError,
    SentinelContractParser,
)


def test_parse_valid_yaml_contract():
    """Verify clean YAML contract parses into typed GoldQualityContract instances."""
    yaml_sample = """
    tables:
      - target_table: "gold_financial_summary"
        source_table: "silver_ledger_events"
        partition_column: "settlement_date"
        time_column: "transaction_timestamp"
        primary_keys: ["settlement_date", "merchant_id", "currency"]
        cadence: "DAILY"
        sla:
          grace_period_hours: 3
          min_expected_rows: 50
        gating_policy: "DEGRADED_WITH_MARKER"
        rolling_windows:
          - name: "7d_settlement"
            window_size_days: 7
            metric_name: "rolling_settlement_7d"
            aggregation_expr: "sum(net_amount)"
            min_completeness_ratio: 0.95
          - name: "30d_chargeback"
            window_size_days: 30
            metric_name: "chargeback_ratio_30d"
            aggregation_expr: "sum(chargeback) / count(1)"
    """

    contracts = SentinelContractParser.load_yaml(yaml_sample)
    assert len(contracts) == 1
    c = contracts[0]

    assert c.target_table == "gold_financial_summary"
    assert c.source_table == "silver_ledger_events"
    assert c.partition_column == "settlement_date"
    assert c.primary_keys == ["settlement_date", "merchant_id", "currency"]
    assert c.cadence == PartitionCadence.DAILY
    assert c.sla_grace_period_hours == 3
    assert c.min_expected_rows == 50
    assert c.gating_policy == GatingPolicy.DEGRADED_WITH_MARKER
    assert len(c.rolling_windows) == 2
    assert c.rolling_windows[0].window_size_days == 7
    assert c.rolling_windows[0].min_completeness_ratio == 0.95


def test_create_accelerators_from_yaml():
    """Verify create_accelerators creates ready-to-run SentinelGoldAccelerator instances."""
    yaml_sample = """
    tables:
      - target_table: "gold_table_a"
        source_table: "silver_table_a"
      - target_table: "gold_table_b"
        source_table: "silver_table_b"
    """

    accelerators = SentinelContractParser.create_accelerators(yaml_sample)
    assert len(accelerators) == 2
    assert "gold_table_a" in accelerators
    assert "gold_table_b" in accelerators

    # Test running check on instantiated accelerator
    acc_a = accelerators["gold_table_a"]
    report = acc_a.run_pipeline_check(
        target_date="2026-10-31",
        available_partitions=["2026-10-31"],
    )
    assert report.can_proceed


def test_malformed_yaml_raises_contract_parsing_error():
    """Missing target_table or source_table should raise ContractParsingError."""
    bad_yaml = """
    tables:
      - target_table: "gold_table_without_source"
    """
    with pytest.raises(ContractParsingError) as exc_info:
        SentinelContractParser.load_yaml(bad_yaml)

    assert "missing required target_table or source_table" in str(exc_info.value).lower()
