"""Tests for GenieBenchmarkRunner and GenieBenchmarkReporter."""

import json
from pathlib import Path

from sentinel.genie_bench.benchmark import (
    GenieBenchmarkRunner,
)
from sentinel.genie_bench.reporter import (
    GenieBenchmarkReporter,
    QualityGateConfig,
)


def test_runner_and_reporter(tmp_path: Path) -> None:
    runner = GenieBenchmarkRunner()
    cases = runner.get_default_enterprise_cases()
    assert len(cases) == 4

    # Perfect generator simulator returning ground truth
    def mock_perfect_generator(prompt: str) -> str:
        case = next(c for c in cases if c.prompt == prompt)
        return case.ground_truth_sql

    suite_result = runner.run_suite(
        suite_name="Enterprise Golden Test Suite",
        cases=cases,
        query_generator=mock_perfect_generator,
    )

    assert suite_result.total_cases == 4
    assert suite_result.passed_cases == 4
    assert suite_result.accuracy == 1.0

    reporter = GenieBenchmarkReporter(
        gate_config=QualityGateConfig(min_overall_accuracy=0.8, min_simple_accuracy=1.0)
    )

    gate = reporter.evaluate_quality_gate(suite_result)
    assert gate.passed is True
    assert gate.reasons == []

    md = reporter.generate_markdown_report(suite_result)
    assert "Databricks Genie Semantic Benchmark" in md
    assert "PASSED" in md
    assert "GENIE-001" in md

    # Export JSON
    out_file = tmp_path / "genie_bench_results.json"
    reporter.export_json(suite_result, out_file)
    assert out_file.exists()
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["suite_name"] == "Enterprise Golden Test Suite"
    assert payload["quality_gate"]["passed"] is True
