"""Unit tests for DeltaMetadataProfiler."""

from sentinel.gold.profiler import DeltaMetadataProfiler


def test_normal_volume_evaluation():
    """Consistent historical volumes should result in a normal non-anomaly evaluation."""
    profiler = DeltaMetadataProfiler("gold_orders")
    history = {
        "2026-10-20": 1000,
        "2026-10-21": 1050,
        "2026-10-22": 980,
        "2026-10-23": 1020,
        "2026-10-24": 990,
        "2026-10-25": 1010,
    }

    result = profiler.detect_volume_anomaly(
        target_date="2026-10-26",
        current_rows=1030,
        historical_partition_counts=history,
        z_threshold=2.5,
    )

    assert not result.is_anomaly
    assert result.anomaly_direction == "NORMAL"
    assert abs(result.z_score) < 2.5
    assert result.confidence_pct == 95.0


def test_severe_volume_drop_anomaly():
    """A sudden 80% volume drop should trigger a DROP anomaly."""
    profiler = DeltaMetadataProfiler("gold_orders")
    history = {
        "2026-10-20": 10000,
        "2026-10-21": 10200,
        "2026-10-22": 9900,
        "2026-10-23": 10100,
        "2026-10-24": 10050,
    }

    result = profiler.detect_volume_anomaly(
        target_date="2026-10-25",
        current_rows=1200,  # 88% drop
        historical_partition_counts=history,
        z_threshold=2.5,
    )

    assert result.is_anomaly
    assert result.anomaly_direction == "DROP"
    assert result.z_score < -2.5
    assert result.row_count == 1200


def test_severe_volume_surge_anomaly():
    """A sudden 400% volume surge should trigger a SURGE anomaly."""
    profiler = DeltaMetadataProfiler("gold_orders")
    history = {
        "2026-10-20": 5000,
        "2026-10-21": 5100,
        "2026-10-22": 4900,
        "2026-10-23": 5050,
        "2026-10-24": 4950,
    }

    result = profiler.detect_volume_anomaly(
        target_date="2026-10-25",
        current_rows=25000,  # 5x spike
        historical_partition_counts=history,
        z_threshold=2.5,
    )

    assert result.is_anomaly
    assert result.anomaly_direction == "SURGE"
    assert result.z_score > 2.5


def test_file_health_fragmentation_detection():
    """Many tiny files in a partition should recommend OPTIMIZE."""
    profiler = DeltaMetadataProfiler("gold_orders")

    # 50 files total 100MB -> avg 2MB per file (< 16MB threshold)
    report = profiler.assess_file_health(
        partition_date="2026-10-26",
        file_count=50,
        total_size_bytes=100 * 1024 * 1024,
    )

    assert report.is_fragmented
    assert report.optimization_recommended
    assert "OPTIMIZE gold_orders" in report.recommended_action
    assert report.avg_file_size_mb == 2.0


def test_profile_partition_savings():
    """Zero-scan metadata profiling should deliver >99% compute reduction."""
    profiler = DeltaMetadataProfiler("gold_orders")
    history = {"2026-10-24": 1000, "2026-10-25": 1050}

    report = profiler.profile_partition(
        target_date="2026-10-26",
        current_rows=1020,
        file_count=4,
        total_size_bytes=512 * 1024 * 1024,  # 512MB
        historical_partition_counts=history,
    )

    assert report.scan_cost_reduction_pct > 99.0
    assert report.metadata_bytes_read == 20 * 1024
