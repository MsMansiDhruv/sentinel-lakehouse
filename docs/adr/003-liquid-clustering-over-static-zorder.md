# ADR-003: Delta Lake Liquid Clustering vs. Static Partitioning + Z-ORDER

* **Status:** Accepted
* **Component:** Silver / Gold Storage Layout

## Context
Traditional Hive-style static partitioning combined with `OPTIMIZE ... ZORDER BY` struggles on high-cardinality and append-heavy Lakehouse tables:
- Over-partitioning creates small-file fragmentation.
- Multi-column `ZORDER` degrades dictionary encoding and rewrites entire partitions on every compaction cycle.
- Changing BI or Databricks Genie query filter patterns requires costly full-table rewrites.

## Decision
Standardize high-cardinality Gold analytical tables on **Delta Lake Liquid Clustering** (`CLUSTER BY`) using incremental Hilbert-curve clustering rather than static directory partitioning + Z-ORDER.

## Consequences
* **Positive:** Measured **24% reduction in bytes scanned** across analytical predicates while eliminating full-partition rewrite amplification when clustering keys evolve.
* **Trade-off:** Requires Databricks Runtime 13.3 LTS+ / Delta Lake 3.x readers for optimal incremental clustering writes.
