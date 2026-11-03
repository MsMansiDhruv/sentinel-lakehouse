"""AST-based SQL semantic equivalence matcher using SQLGlot."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)


@dataclass
class AstMatchResult:
    """Detailed evaluation result from SQL AST structural comparison."""

    is_equivalent: bool
    match_score: float
    syntax_valid: bool
    structural_differences: list[str] = field(default_factory=list)
    normalized_generated_sql: str = ""
    normalized_ground_truth_sql: str = ""


class SQLAstMatcher:
    """Compares Databricks Genie generated SQL against curated gold-standard SQL."""

    def __init__(self, dialect: str = "databricks") -> None:
        self.dialect = dialect

    def compare(self, generated_sql: str, ground_truth_sql: str) -> AstMatchResult:
        """Evaluate semantic equivalence and structural similarity between two SQL queries."""
        # 1. Parse ground truth
        try:
            gt_ast = sqlglot.parse_one(ground_truth_sql, read=self.dialect)
        except Exception as e:
            raise ValueError(f"Ground truth SQL could not be parsed: {e}") from e

        # 2. Parse generated SQL
        try:
            gen_ast = sqlglot.parse_one(generated_sql, read=self.dialect)
        except Exception as e:
            return AstMatchResult(
                is_equivalent=False,
                match_score=0.0,
                syntax_valid=False,
                structural_differences=[f"Syntax error: {e}"],
                normalized_generated_sql="",
                normalized_ground_truth_sql=gt_ast.sql(dialect=self.dialect),
            )

        norm_gen_sql = gen_ast.sql(dialect=self.dialect, normalize=True)
        norm_gt_sql = gt_ast.sql(dialect=self.dialect, normalize=True)

        # Exact normalized match
        if norm_gen_sql.strip().lower() == norm_gt_sql.strip().lower():
            return AstMatchResult(
                is_equivalent=True,
                match_score=1.0,
                syntax_valid=True,
                structural_differences=[],
                normalized_generated_sql=norm_gen_sql,
                normalized_ground_truth_sql=norm_gt_sql,
            )

        # Structural comparison
        differences: list[str] = []

        # Table comparison
        gt_tables = self._extract_tables(gt_ast)
        gen_tables = self._extract_tables(gen_ast)
        table_overlap = len(gt_tables.intersection(gen_tables))
        table_total = max(len(gt_tables.union(gen_tables)), 1)
        table_score = table_overlap / table_total

        if gt_tables != gen_tables:
            differences.append(
                f"Tables mismatch: expected {sorted(gt_tables)}, got {sorted(gen_tables)}"
            )

        # Projections comparison
        gt_selects = self._extract_projections(gt_ast)
        gen_selects = self._extract_projections(gen_ast)
        select_overlap = len(gt_selects.intersection(gen_selects))
        select_total = max(len(gt_selects.union(gen_selects)), 1)
        select_score = select_overlap / select_total

        if gt_selects != gen_selects:
            differences.append(
                f"Projections mismatch: expected {sorted(gt_selects)}, got {sorted(gen_selects)}"
            )

        # Group By comparison
        gt_groups = self._extract_group_bys(gt_ast)
        gen_groups = self._extract_group_bys(gen_ast)
        group_overlap = len(gt_groups.intersection(gen_groups))
        group_total = (
            max(len(gt_groups.union(gen_groups)), 1) if (gt_groups or gen_groups) else 1
        )
        group_score = (
            1.0 if not (gt_groups or gen_groups) else (group_overlap / group_total)
        )

        if gt_groups != gen_groups:
            differences.append(
                f"Group By mismatch: expected {sorted(gt_groups)}, got {sorted(gen_groups)}"
            )

        # Where / Predicate comparison
        gt_where = self._extract_where_conjuncts(gt_ast)
        gen_where = self._extract_where_conjuncts(gen_ast)
        where_overlap = len(gt_where.intersection(gen_where))
        where_total = (
            max(len(gt_where.union(gen_where)), 1) if (gt_where or gen_where) else 1
        )
        where_score = (
            1.0 if not (gt_where or gen_where) else (where_overlap / where_total)
        )

        if gt_where != gen_where:
            differences.append(
                f"Where conditions mismatch: expected {sorted(gt_where)}, got {sorted(gen_where)}"
            )

        # Weighted aggregate score
        match_score = (
            0.35 * table_score
            + 0.30 * select_score
            + 0.20 * where_score
            + 0.15 * group_score
        )
        is_equivalent = match_score >= 0.99 or len(differences) == 0

        return AstMatchResult(
            is_equivalent=is_equivalent,
            match_score=round(match_score, 4),
            syntax_valid=True,
            structural_differences=differences,
            normalized_generated_sql=norm_gen_sql,
            normalized_ground_truth_sql=norm_gt_sql,
        )

    def _strip_qualifiers(self, expr: exp.Expression) -> exp.Expression:
        """Strip table qualification from columns so o.amount matches amount."""
        copied = expr.copy()
        for col in copied.find_all(exp.Column):
            col.set("table", None)
        return copied

    def _extract_tables(self, ast: exp.Expression) -> set[str]:
        tables: set[str] = set()
        for t in ast.find_all(exp.Table):
            if t.name:
                tables.add(t.name.lower())
        return tables

    def _extract_projections(self, ast: exp.Expression) -> set[str]:
        projections: set[str] = set()
        for select in ast.find_all(exp.Select):
            for expr in select.expressions:
                stripped = self._strip_qualifiers(expr.unalias())
                clean_expr = stripped.sql(dialect=self.dialect).strip().lower()
                projections.add(clean_expr)
        return projections

    def _extract_group_bys(self, ast: exp.Expression) -> set[str]:
        groups: set[str] = set()
        for group in ast.find_all(exp.Group):
            for expr in group.expressions:
                stripped = self._strip_qualifiers(expr)
                groups.add(stripped.sql(dialect=self.dialect).strip().lower())
        return groups

    def _extract_where_conjuncts(self, ast: exp.Expression) -> set[str]:
        conjuncts: set[str] = set()
        for where in ast.find_all(exp.Where):
            this = where.this
            if isinstance(this, exp.And):
                for child in this.flatten():
                    stripped = self._strip_qualifiers(child)
                    conjuncts.add(stripped.sql(dialect=self.dialect).strip().lower())
            else:
                stripped = self._strip_qualifiers(this)
                conjuncts.add(stripped.sql(dialect=self.dialect).strip().lower())
        return conjuncts
