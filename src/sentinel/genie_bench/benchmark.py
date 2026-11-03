"""Benchmarking engine for Databricks Genie and Text-to-SQL semantic layers."""

from __future__ import annotations

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sentinel.genie_bench.ast_matcher import AstMatchResult, SQLAstMatcher


class ComplexityTier(str, enum.Enum):
    """Complexity classification for Genie benchmark test cases."""

    SIMPLE = "simple"
    MULTI_JOIN = "multi_join"
    WINDOW_AGGREGATION = "window_aggregation"
    SUBQUERY_CTE = "subquery_cte"


@dataclass
class BenchmarkCase:
    """A curated test case for Genie evaluation."""

    case_id: str
    prompt: str
    ground_truth_sql: str
    complexity: ComplexityTier
    expected_tables: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    """Execution and evaluation result of an individual benchmark case."""

    case: BenchmarkCase
    generated_sql: str
    ast_match: AstMatchResult
    execution_time_ms: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case.case_id,
            "prompt": self.case.prompt,
            "complexity": self.case.complexity.value,
            "passed": self.passed,
            "match_score": self.ast_match.match_score,
            "syntax_valid": self.ast_match.syntax_valid,
            "execution_time_ms": self.execution_time_ms,
            "differences": self.ast_match.structural_differences,
            "generated_sql": self.generated_sql,
            "ground_truth_sql": self.case.ground_truth_sql,
        }


@dataclass
class BenchmarkSuiteResult:
    """Aggregated evaluation metrics across the entire benchmark suite."""

    suite_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    accuracy: float
    tier_accuracy: dict[str, float] = field(default_factory=dict)
    average_latency_ms: float = 0.0
    results: list[BenchmarkResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "accuracy": self.accuracy,
            "tier_accuracy": self.tier_accuracy,
            "average_latency_ms": self.average_latency_ms,
            "results": [r.to_dict() for r in self.results],
        }


class GenieBenchmarkRunner:
    """Runner for executing and grading Databricks Genie query generation."""

    def __init__(
        self,
        matcher: SQLAstMatcher | None = None,
        min_pass_score: float = 0.85,
    ) -> None:
        self.matcher = matcher or SQLAstMatcher()
        self.min_pass_score = min_pass_score

    def run_suite(
        self,
        suite_name: str,
        cases: list[BenchmarkCase],
        query_generator: Callable[[str], str],
    ) -> BenchmarkSuiteResult:
        """Execute the benchmark suite against a query generation callable."""
        results: list[BenchmarkResult] = []
        tier_totals: dict[str, int] = {}
        tier_passed: dict[str, int] = {}
        total_time_ms = 0.0

        for case in cases:
            t0 = time.perf_counter()
            try:
                gen_sql = query_generator(case.prompt)
            except Exception as e:
                gen_sql = f"-- Error generating query: {e}"
            t1 = time.perf_counter()
            elapsed_ms = (t1 - t0) * 1000.0
            total_time_ms += elapsed_ms

            ast_match = self.matcher.compare(gen_sql, case.ground_truth_sql)
            passed = (
                ast_match.is_equivalent or ast_match.match_score >= self.min_pass_score
            )

            result = BenchmarkResult(
                case=case,
                generated_sql=gen_sql,
                ast_match=ast_match,
                execution_time_ms=round(elapsed_ms, 2),
                passed=passed,
            )
            results.append(result)

            c_tier = case.complexity.value
            tier_totals[c_tier] = tier_totals.get(c_tier, 0) + 1
            if passed:
                tier_passed[c_tier] = tier_passed.get(c_tier, 0) + 1

        total = len(cases)
        passed_count = sum(1 for r in results if r.passed)
        failed_count = total - passed_count
        accuracy = round((passed_count / total), 4) if total > 0 else 0.0

        tier_accuracy = {
            tier: round(tier_passed.get(tier, 0) / tier_totals[tier], 4)
            for tier in tier_totals
        }
        avg_latency = round(total_time_ms / total, 2) if total > 0 else 0.0

        return BenchmarkSuiteResult(
            suite_name=suite_name,
            total_cases=total,
            passed_cases=passed_count,
            failed_cases=failed_count,
            accuracy=accuracy,
            tier_accuracy=tier_accuracy,
            average_latency_ms=avg_latency,
            results=results,
        )

    @staticmethod
    def get_default_enterprise_cases() -> list[BenchmarkCase]:
        """Curated enterprise benchmark cases testing single table, joins, windowing, and CTEs."""
        return [
            BenchmarkCase(
                case_id="GENIE-001",
                prompt="What is our total revenue by product category in 2026?",
                ground_truth_sql=(
                    "SELECT category, SUM(amount) AS total_revenue "
                    "FROM main.gold.orders "
                    "WHERE YEAR(order_date) = 2026 "
                    "GROUP BY category"
                ),
                complexity=ComplexityTier.SIMPLE,
                expected_tables=["main.gold.orders"],
                tags=["aggregation", "finance"],
            ),
            BenchmarkCase(
                case_id="GENIE-002",
                prompt="Show top 10 customers by lifetime spend along with their segment name.",
                ground_truth_sql=(
                    "SELECT c.customer_id, c.customer_name, s.segment_name, SUM(o.amount) AS lifetime_spend "
                    "FROM main.gold.customers AS c "
                    "JOIN main.gold.segments AS s ON c.segment_id = s.segment_id "
                    "JOIN main.gold.orders AS o ON c.customer_id = o.customer_id "
                    "GROUP BY c.customer_id, c.customer_name, s.segment_name "
                    "ORDER BY lifetime_spend DESC "
                    "LIMIT 10"
                ),
                complexity=ComplexityTier.MULTI_JOIN,
                expected_tables=[
                    "main.gold.customers",
                    "main.gold.segments",
                    "main.gold.orders",
                ],
                tags=["multi_join", "ranking"],
            ),
            BenchmarkCase(
                case_id="GENIE-003",
                prompt="Calculate month-over-month revenue growth percentage for 2026.",
                ground_truth_sql=(
                    "SELECT month, monthly_revenue, "
                    "LAG(monthly_revenue, 1) OVER (ORDER BY month) AS prev_month_revenue, "
                    "((monthly_revenue - LAG(monthly_revenue, 1) OVER (ORDER BY month)) / "
                    "LAG(monthly_revenue, 1) OVER (ORDER BY month)) * 100 AS growth_pct "
                    "FROM ( "
                    "  SELECT DATE_TRUNC('month', order_date) AS month, SUM(amount) AS monthly_revenue "
                    "  FROM main.gold.orders "
                    "  WHERE YEAR(order_date) = 2026 "
                    "  GROUP BY DATE_TRUNC('month', order_date) "
                    ")"
                ),
                complexity=ComplexityTier.WINDOW_AGGREGATION,
                expected_tables=["main.gold.orders"],
                tags=["window_function", "mom_growth"],
            ),
            BenchmarkCase(
                case_id="GENIE-004",
                prompt="Find customers who placed an order in Q1 2026 but had no orders in Q2 2026.",
                ground_truth_sql=(
                    "WITH q1_buyers AS ( "
                    "  SELECT DISTINCT customer_id FROM main.gold.orders "
                    "  WHERE order_date BETWEEN '2026-01-01' AND '2026-03-31' "
                    "), "
                    "q2_buyers AS ( "
                    "  SELECT DISTINCT customer_id FROM main.gold.orders "
                    "  WHERE order_date BETWEEN '2026-04-01' AND '2026-06-30' "
                    ") "
                    "SELECT q1.customer_id "
                    "FROM q1_buyers AS q1 "
                    "LEFT JOIN q2_buyers AS q2 ON q1.customer_id = q2.customer_id "
                    "WHERE q2.customer_id IS NULL"
                ),
                complexity=ComplexityTier.SUBQUERY_CTE,
                expected_tables=["main.gold.orders"],
                tags=["cte", "churn"],
            ),
        ]
