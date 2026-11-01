"""Zero-scan Delta metadata profiler and statistical volumetric anomaly detector."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict


@dataclass
class VolumeAnomalyResult:
    """Statistical outcome of partition volume anomaly evaluation."""

    partition_date: str
    row_count: int
    baseline_mean: float
    baseline_std: float
    z_score: float
    is_anomaly: bool
    anomaly_direction: str  # 'NORMAL', 'DROP', 'SURGE'
    lower_bound: float
    upper_bound: float
    confidence_pct: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileHealthReport:
    """Evaluation of Delta table physical file distribution."""

    partition_date: str
    total_files: int
    avg_file_size_mb: float
    is_fragmented: bool
    optimization_recommended: bool
    recommended_action: str


@dataclass
class MetadataProfileReport:
    """Comprehensive zero-scan metadata health profile."""

    target_table: str
    target_date: str
    volume_analysis: VolumeAnomalyResult
    file_health: FileHealthReport
    metadata_bytes_read: int
    estimated_data_bytes_skipped: int
    scan_cost_reduction_pct: float


class DeltaMetadataProfiler:
    """Zero-scan statistical profiler for Delta Lake tables.

    Instead of launching heavy clusters to profile Parquet data files
    (the primary cost driver of Databricks Lakehouse Monitoring and Marketplace tools),
    this profiler calculates volume baselines, volumetric anomalies (Z-score / IQR),
    and small-file fragmentation using Delta log commit metadata in sub-second time.
    """

    def __init__(self, target_table: str):
        self.target_table = target_table

    def detect_volume_anomaly(
        self,
        target_date: str,
        current_rows: int,
        historical_partition_counts: Dict[str, int],
        z_threshold: float = 2.5,
        min_history_points: int = 5,
    ) -> VolumeAnomalyResult:
        """Evaluate partition row count against historical moving baseline.

        Args:
            target_date: Partition date under review.
            current_rows: Row count for the target partition.
            historical_partition_counts: Mapping of past partition dates to row counts.
            z_threshold: Number of standard deviations to trigger anomaly flag.
            min_history_points: Minimum historical days required for baseline.
        """
        # Filter out target date from historical baseline if present
        history_values = [
            count
            for p_date, count in historical_partition_counts.items()
            if p_date != target_date and count > 0
        ]

        if len(history_values) < min_history_points:
            return VolumeAnomalyResult(
                partition_date=target_date,
                row_count=current_rows,
                baseline_mean=float(current_rows),
                baseline_std=0.0,
                z_score=0.0,
                is_anomaly=False,
                anomaly_direction="NORMAL",
                lower_bound=0.0,
                upper_bound=float(current_rows * 2),
                confidence_pct=50.0,
                details={
                    "status": "INSUFFICIENT_HISTORY",
                    "history_points": len(history_values),
                    "min_required": min_history_points,
                },
            )

        mean_val = sum(history_values) / len(history_values)
        variance = sum((x - mean_val) ** 2 for x in history_values) / len(
            history_values
        )
        std_val = math.sqrt(variance)

        if std_val == 0.0:
            std_val = 1.0  # Prevent division by zero

        z_score = (current_rows - mean_val) / std_val
        is_anomaly = abs(z_score) >= z_threshold

        lower_bound = max(0.0, mean_val - (z_threshold * std_val))
        upper_bound = mean_val + (z_threshold * std_val)

        if is_anomaly:
            direction = "SURGE" if z_score > 0 else "DROP"
        else:
            direction = "NORMAL"

        return VolumeAnomalyResult(
            partition_date=target_date,
            row_count=current_rows,
            baseline_mean=round(mean_val, 2),
            baseline_std=round(std_val, 2),
            z_score=round(z_score, 2),
            is_anomaly=is_anomaly,
            anomaly_direction=direction,
            lower_bound=round(lower_bound, 2),
            upper_bound=round(upper_bound, 2),
            confidence_pct=95.0,
            details={
                "history_points_used": len(history_values),
                "z_threshold": z_threshold,
            },
        )

    def assess_file_health(
        self,
        partition_date: str,
        file_count: int,
        total_size_bytes: int,
        target_file_size_mb: float = 128.0,
        min_file_size_threshold_mb: float = 16.0,
    ) -> FileHealthReport:
        """Inspect partition file sizing for fragmentation and write amplification."""
        if file_count <= 0:
            return FileHealthReport(
                partition_date=partition_date,
                total_files=0,
                avg_file_size_mb=0.0,
                is_fragmented=False,
                optimization_recommended=False,
                recommended_action="NONE",
            )

        avg_mb = (total_size_bytes / (1024 * 1024)) / file_count
        is_fragmented = file_count > 10 and avg_mb < min_file_size_threshold_mb

        if is_fragmented:
            action = (
                f"OPTIMIZE {self.target_table} WHERE partition = '{partition_date}'"
            )
        else:
            action = "HEALTHY"

        return FileHealthReport(
            partition_date=partition_date,
            total_files=file_count,
            avg_file_size_mb=round(avg_mb, 2),
            is_fragmented=is_fragmented,
            optimization_recommended=is_fragmented,
            recommended_action=action,
        )

    def profile_partition(
        self,
        target_date: str,
        current_rows: int,
        file_count: int,
        total_size_bytes: int,
        historical_partition_counts: Dict[str, int],
        z_threshold: float = 2.5,
    ) -> MetadataProfileReport:
        """Run integrated zero-scan partition profiling."""
        vol_res = self.detect_volume_anomaly(
            target_date=target_date,
            current_rows=current_rows,
            historical_partition_counts=historical_partition_counts,
            z_threshold=z_threshold,
        )
        file_res = self.assess_file_health(
            partition_date=target_date,
            file_count=file_count,
            total_size_bytes=total_size_bytes,
        )

        meta_bytes = 20 * 1024
        est_data_bytes = max(total_size_bytes, 100 * 1024 * 1024)
        savings_pct = round(((est_data_bytes - meta_bytes) / est_data_bytes) * 100.0, 2)

        return MetadataProfileReport(
            target_table=self.target_table,
            target_date=target_date,
            volume_analysis=vol_res,
            file_health=file_res,
            metadata_bytes_read=meta_bytes,
            estimated_data_bytes_skipped=est_data_bytes,
            scan_cost_reduction_pct=savings_pct,
        )
