"""Scorecard reporting and CI/CD quality gate enforcement for Genie-Bench."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sentinel.genie_bench.benchmark import BenchmarkSuiteResult


@dataclass
class QualityGateConfig:
    """CI/CD thresholds required for benchmark validation pass."""

    min_overall_accuracy: float = 0.75
    min_simple_accuracy: float = 1.00
    max_average_latency_ms: float = 8000.0


@dataclass
class QualityGateResult:
    """Outcome of quality gate evaluation."""

    passed: bool
    reasons: list[str]


class GenieBenchmarkReporter:
    """Renders executive scorecards and enforces CI quality gates."""

    def __init__(self, gate_config: QualityGateConfig | None = None) -> None:
        self.gate_config = gate_config or QualityGateConfig()

    def evaluate_quality_gate(
        self, suite_result: BenchmarkSuiteResult
    ) -> QualityGateResult:
        """Verify whether benchmark results meet quality gate criteria."""
        reasons: list[str] = []
        passed = True

        if suite_result.accuracy < self.gate_config.min_overall_accuracy:
            passed = False
            reasons.append(
                f"Overall accuracy {suite_result.accuracy:.1%} is below required threshold {self.gate_config.min_overall_accuracy:.1%}"
            )

        simple_acc = suite_result.tier_accuracy.get("simple", 1.0)
        if simple_acc < self.gate_config.min_simple_accuracy:
            passed = False
            reasons.append(
                f"Simple query accuracy {simple_acc:.1%} is below required threshold {self.gate_config.min_simple_accuracy:.1%}"
            )

        if suite_result.average_latency_ms > self.gate_config.max_average_latency_ms:
            passed = False
            reasons.append(
                f"Average latency {suite_result.average_latency_ms:.1f}ms exceeds threshold {self.gate_config.max_average_latency_ms:.1f}ms"
            )

        return QualityGateResult(passed=passed, reasons=reasons)

    def generate_markdown_report(self, suite_result: BenchmarkSuiteResult) -> str:
        """Generate executive Markdown scorecard."""
        gate = self.evaluate_quality_gate(suite_result)
        gate_status = "PASSED" if gate.passed else "FAILED"

        lines = [
            f"# Databricks Genie Semantic Benchmark: {suite_result.suite_name}",
            "",
            f"**Quality Gate Status**: `{gate_status}`",
            f"- **Overall Accuracy**: `{suite_result.accuracy:.1%}` ({suite_result.passed_cases}/{suite_result.total_cases})",
            f"- **Average Generation Latency**: `{suite_result.average_latency_ms:.2f} ms`",
            "",
            "## Complexity Breakdown",
            "",
            "| Complexity Tier | Accuracy | Total Cases |",
            "| :--- | :--- | :--- |",
        ]

        for tier, acc in sorted(suite_result.tier_accuracy.items()):
            count = sum(
                1 for r in suite_result.results if r.case.complexity.value == tier
            )
            lines.append(f"| `{tier}` | `{acc:.1%}` | {count} |")

        lines.extend(
            [
                "",
                "## Test Case Details",
                "",
                "| ID | Prompt | Complexity | Result | Score | Latency |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )

        for r in suite_result.results:
            status = "PASS" if r.passed else "FAIL"
            clean_prompt = r.case.prompt.replace("|", "\\|")
            lines.append(
                f"| `{r.case.case_id}` | {clean_prompt} | `{r.case.complexity.value}` | `{status}` | `{r.ast_match.match_score:.2f}` | `{r.execution_time_ms:.1f}ms` |"
            )

        if not gate.passed:
            lines.extend(
                [
                    "",
                    "### Quality Gate Failures",
                    "",
                ]
            )
            for reason in gate.reasons:
                lines.append(f"- {reason}")

        return "\n".join(lines) + "\n"

    def export_json(
        self, suite_result: BenchmarkSuiteResult, output_path: Path | str
    ) -> None:
        """Persist benchmark execution results as JSON artifact."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = suite_result.to_dict()
        gate = self.evaluate_quality_gate(suite_result)
        data["quality_gate"] = {"passed": gate.passed, "reasons": gate.reasons}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
