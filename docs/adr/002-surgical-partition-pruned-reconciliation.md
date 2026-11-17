# ADR-002: Surgical Partition-Pruned Delta MERGE vs. Full-Table Backfills

* **Status:** Accepted
* **Component:** `sentinel.autoheal_de`

## Context
Upstream late-arriving data and schema anomalies often invalidate historical windows in Medallion Silver/Gold tables. Standard recovery runbooks trigger full-table overwrites or wide rolling-window `MERGE` jobs, causing massive Parquet rewrite amplification and long downstream SLA misses.

## Decision
Use **zero-scan Delta transaction log (`_delta_log`) inspection** to identify the exact affected partition keys and timestamps, bounding the blast radius before generating a **partition-pruned `MERGE` statement** targeting only impacted partitions.

## Consequences
* **Positive:** Minimizes I/O and compute cost during incident recovery while preserving Delta time-travel auditability.
* **Trade-off:** Requires strict partition key discipline or Liquid Clustering metadata alignment so target predicates prune cleanly at the file-skipping layer.
