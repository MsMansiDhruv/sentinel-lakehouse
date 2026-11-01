"""Universal plug-and-play declarative contract parser for Sentinel Lakehouse."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union
import yaml

from sentinel.gold.accelerator import SentinelGoldAccelerator
from sentinel.gold.config import (
    GatingPolicy,
    GoldQualityContract,
    PartitionCadence,
    RollingWindowSpec,
)


class ContractParsingError(Exception):
    """Raised when a declarative contract YAML or dictionary is malformed."""

    pass


class SentinelContractParser:
    """Parses declarative YAML/JSON quality contracts for any Databricks lakehouse project.

    Enables plug-and-play adoption across diverse data domains without boilerplate pipeline code.
    """

    @staticmethod
    def parse_dict(config: Dict[str, Any]) -> List[GoldQualityContract]:
        """Parse dictionary configuration into a list of typed GoldQualityContract objects."""
        tables_data = config.get("tables", [])
        if not tables_data and "target_table" in config:
            tables_data = [config]

        if not tables_data:
            raise ContractParsingError("No table contracts defined in configuration.")

        contracts: List[GoldQualityContract] = []

        for tbl in tables_data:
            target_table = tbl.get("target_table")
            source_table = tbl.get("source_table")
            if not target_table or not source_table:
                raise ContractParsingError(
                    f"Contract missing required target_table or source_table: {tbl}"
                )

            partition_col = tbl.get("partition_column", "order_date")
            time_col = tbl.get("time_column", partition_col)
            primary_keys = tbl.get("primary_keys", [partition_col])

            cadence_str = tbl.get("cadence", "DAILY").upper()
            cadence = (
                PartitionCadence.HOURLY
                if cadence_str == "HOURLY"
                else PartitionCadence.DAILY
            )

            sla_cfg = tbl.get("sla", {})
            grace_hours = sla_cfg.get("grace_period_hours", 4)
            min_rows = sla_cfg.get("min_expected_rows", 1)

            policy_str = tbl.get("gating_policy", "DEGRADED_WITH_MARKER").upper()
            try:
                policy = GatingPolicy(policy_str)
            except ValueError:
                policy = GatingPolicy.DEGRADED_WITH_MARKER

            # Parse rolling window specifications
            window_specs: List[RollingWindowSpec] = []
            for w in tbl.get("rolling_windows", []):
                window_specs.append(
                    RollingWindowSpec(
                        name=w["name"],
                        window_size_days=int(w.get("window_size_days", 7)),
                        metric_name=w.get("metric_name", w["name"]),
                        aggregation_expr=w.get("aggregation_expr", "count(1)"),
                        time_column=w.get("time_column", time_col),
                        partition_column=w.get("partition_column", partition_col),
                        min_completeness_ratio=float(
                            w.get("min_completeness_ratio", 1.0)
                        ),
                    )
                )

            contract = GoldQualityContract(
                target_table=target_table,
                source_table=source_table,
                time_column=time_col,
                partition_column=partition_col,
                primary_keys=primary_keys,
                cadence=cadence,
                sla_grace_period_hours=grace_hours,
                min_expected_rows=min_rows,
                gating_policy=policy,
                rolling_windows=window_specs,
                metadata=tbl.get("metadata", {}),
            )
            contracts.append(contract)

        return contracts

    @classmethod
    def load_yaml(
        cls, yaml_content_or_path: Union[str, Path]
    ) -> List[GoldQualityContract]:
        """Load and parse contracts from a YAML string or file path."""
        data = None
        if isinstance(yaml_content_or_path, Path):
            with open(yaml_content_or_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        elif isinstance(yaml_content_or_path, str):
            if "\n" not in yaml_content_or_path and len(yaml_content_or_path) < 255:
                p = Path(yaml_content_or_path)
                try:
                    if p.is_file():
                        with open(p, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                except OSError:
                    pass
            if data is None:
                data = yaml.safe_load(yaml_content_or_path)
        else:
            raise ContractParsingError("Input must be a YAML string or Path.")

        if not isinstance(data, dict):
            raise ContractParsingError("YAML root must be a dictionary.")

        return cls.parse_dict(data)

    @classmethod
    def create_accelerators(
        cls,
        yaml_content_or_path: Union[str, Path],
    ) -> Dict[str, SentinelGoldAccelerator]:
        """Instantiate ready-to-run SentinelGoldAccelerators keyed by target table."""
        contracts = cls.load_yaml(yaml_content_or_path)
        return {c.target_table: SentinelGoldAccelerator(c) for c in contracts}
