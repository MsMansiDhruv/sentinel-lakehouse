"""Evaluation harness and benchmark scorecard for Sentinel-GenAI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

from sentinel.genai.compound_router import CompoundQueryRouter, QueryIntent


@dataclass
class EvalTestCase:
    """A parameterized test case for evaluating GenAI performance."""

    prompt: str
    expected_intent: QueryIntent
    expected_keywords: list[str] = field(default_factory=list)
    expected_tables: list[str] = field(default_factory=list)


@dataclass
class EvalMetricResult:
    """Individual test evaluation metric score."""

    prompt: str
    intent_match: bool
    context_relevance: float  # 0.0 to 1.0
    guardrail_passed: bool
    latency_ms: float


@dataclass
class BenchmarkScorecard:
    """Aggregated evaluation scorecard across test cases."""

    total_cases: int
    intent_accuracy: float
    avg_context_relevance: float
    guardrail_pass_rate: float
    avg_latency_ms: float
    results: list[EvalMetricResult]

    def to_markdown(self) -> str:
        """Render evaluation benchmark results as a clean Markdown report."""
        lines = [
            "# Sentinel-GenAI Benchmark Scorecard\n",
            f"- **Total Test Cases**: {self.total_cases}",
            f"- **Intent Accuracy**: {self.intent_accuracy:.1%}",
            f"- **Average Context Relevance**: {self.avg_context_relevance:.1%}",
            f"- **Guardrail Pass Rate**: {self.guardrail_pass_rate:.1%}",
            f"- **Average Latency**: {self.avg_latency_ms:.2f} ms\n",
            "| Prompt | Intent Match | Relevance | Guardrail | Latency (ms) |",
            "| :--- | :---: | :---: | :---: | :---: |",
        ]
        for r in self.results:
            intent_icon = "PASS" if r.intent_match else "FAIL"
            guard_icon = "PASS" if r.guardrail_passed else "FAIL"
            clean_prompt = r.prompt[:40] + "..." if len(r.prompt) > 40 else r.prompt
            lines.append(
                f"| `{clean_prompt}` | {intent_icon} | {r.context_relevance:.0%} | {guard_icon} | {r.latency_ms:.1f} |"
            )
        return "\n".join(lines)


class GenAIEvaluator:
    """Evaluation runner assessing accuracy, relevance, and guardrail compliance."""

    def __init__(self, router: CompoundQueryRouter) -> None:
        self.router = router

    def evaluate(self, test_cases: Sequence[EvalTestCase]) -> BenchmarkScorecard:
        """Execute evaluation across the supplied test suite."""
        if not test_cases:
            raise ValueError("Test cases list cannot be empty.")

        results: list[EvalMetricResult] = []

        for tc in test_cases:
            start_t = time.perf_counter()
            response = self.router.route_and_execute(tc.prompt)
            duration_ms = (time.perf_counter() - start_t) * 1000.0

            intent_match = response.intent == tc.expected_intent

            # Context relevance: fraction of expected keywords found in retrieved chunks or answer
            relevance = 1.0
            if tc.expected_keywords:
                full_text = (
                    response.answer.lower()
                    + " "
                    + " ".join(
                        c.chunk.content.lower() for c in response.retrieved_chunks
                    )
                )
                found = sum(1 for kw in tc.expected_keywords if kw.lower() in full_text)
                relevance = found / len(tc.expected_keywords)

            results.append(
                EvalMetricResult(
                    prompt=tc.prompt,
                    intent_match=intent_match,
                    context_relevance=relevance,
                    guardrail_passed=response.guardrail_passed,
                    latency_ms=duration_ms,
                )
            )

        total = len(results)
        intent_acc = sum(1 for r in results if r.intent_match) / total
        avg_rel = sum(r.context_relevance for r in results) / total
        guard_rate = sum(1 for r in results if r.guardrail_passed) / total
        avg_lat = sum(r.latency_ms for r in results) / total

        return BenchmarkScorecard(
            total_cases=total,
            intent_accuracy=intent_acc,
            avg_context_relevance=avg_rel,
            guardrail_pass_rate=guard_rate,
            avg_latency_ms=avg_lat,
            results=results,
        )
