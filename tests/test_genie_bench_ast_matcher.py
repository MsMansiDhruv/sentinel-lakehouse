"""Tests for SQLAstMatcher semantic equivalence evaluation."""

from sentinel.genie_bench.ast_matcher import SQLAstMatcher


def test_matcher_exact_normalized_match() -> None:
    matcher = SQLAstMatcher(dialect="databricks")
    gt = "SELECT category, SUM(amount) AS rev FROM main.gold.orders WHERE year(order_date) = 2026 GROUP BY category"
    gen = "SELECT category, SUM(amount) AS rev FROM main.gold.orders WHERE year(order_date) = 2026 GROUP BY category"
    res = matcher.compare(gen, gt)
    assert res.is_equivalent is True
    assert res.match_score == 1.0
    assert res.syntax_valid is True
    assert len(res.structural_differences) == 0


def test_matcher_alias_and_casing_insensitivity() -> None:
    matcher = SQLAstMatcher(dialect="databricks")
    gt = "SELECT o.category, sum(o.amount) FROM main.gold.orders AS o GROUP BY o.category"
    gen = "SELECT category, SUM(amount) FROM main.gold.orders GROUP BY category"
    res = matcher.compare(gen, gt)
    assert res.is_equivalent is True
    assert res.match_score >= 0.95


def test_matcher_table_mismatch() -> None:
    matcher = SQLAstMatcher(dialect="databricks")
    gt = "SELECT id FROM main.gold.orders"
    gen = "SELECT id FROM main.bronze.raw_orders"
    res = matcher.compare(gen, gt)
    assert res.is_equivalent is False
    assert any("Tables mismatch" in d for d in res.structural_differences)


def test_matcher_projection_mismatch() -> None:
    matcher = SQLAstMatcher(dialect="databricks")
    gt = "SELECT id, amount, customer_id FROM main.gold.orders"
    gen = "SELECT id, amount FROM main.gold.orders"
    res = matcher.compare(gen, gt)
    assert res.is_equivalent is False
    assert any("Projections mismatch" in d for d in res.structural_differences)


def test_matcher_invalid_syntax() -> None:
    matcher = SQLAstMatcher(dialect="databricks")
    gt = "SELECT id FROM main.gold.orders"
    gen = "SELECT FROM WHERE"
    res = matcher.compare(gen, gt)
    assert res.is_equivalent is False
    assert res.syntax_valid is False
    assert res.match_score == 0.0
