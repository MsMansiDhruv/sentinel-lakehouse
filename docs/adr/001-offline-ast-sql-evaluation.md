# ADR-001: Offline SQLGlot AST Equivalence in CI/CD

* **Status:** Accepted
* **Component:** `sentinel.genie_bench.ast_matcher`

## Context
Evaluating Text-to-SQL and Databricks Genie outputs on every Pull Request requires comparing LLM-generated SQL against curated ground-truth queries. Two naive approaches fail in production:
1. **Exact string matching (`assert gen == gt`):** Breaks constantly on valid semantic variations—different CTE aliases (`ms` vs `monthly_sales`), qualified columns (`o.amount` vs `amount`), or commutative predicate ordering.
2. **Live Databricks SQL Warehouse execution in CI:** Requires active cluster credentials in GitHub Actions, warms up compute, and adds 2–3 minutes + DBU burn per PR benchmark run.

## Decision
Implement an **offline, dialect-aware AST equivalence matcher** (`SQLAstMatcher`) using `sqlglot`:
- Parses both generated and ground-truth SQL into Databricks/Spark dialect ASTs.
- Isolates local CTE scopes (`_extract_cte_names`) so internal CTE alias variations do not trigger false physical catalog/table mismatches.
- Normalizes table qualifiers, column aliases, and commutative predicates before structural comparison.

## Consequences
* **Positive:** Evaluates benchmark suites offline in runner memory in **~85ms** with **0 DBU overhead** and zero secret exposure in PR CI.
* **Trade-off:** Verifies structural and syntactic intent rather than data-dependent runtime equivalence (e.g., `INNER JOIN` vs `EXISTS`). End-to-end warehouse execution is reserved for scheduled integration gates.
