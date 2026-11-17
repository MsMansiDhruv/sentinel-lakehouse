# Architecture Decision Records (ADRs)

This directory documents key architectural trade-offs and design decisions made in **Sentinel Lakehouse**.

| ADR | Title | Status | Focus |
| :--- | :--- | :--- | :--- |
| [ADR-001](./001-offline-ast-sql-evaluation.md) | Offline SQLGlot AST Equivalence in CI/CD | Accepted | Genie-Bench · Zero-DBU Testing |
| [ADR-002](./002-surgical-partition-pruned-reconciliation.md) | Surgical Partition-Pruned Delta MERGE vs. Full-Table Backfills | Accepted | AutoHeal-DE · Blast-Radius Bounding |
| [ADR-003](./003-liquid-clustering-over-static-zorder.md) | Delta Lake Liquid Clustering vs. Static Partitioning + Z-ORDER | Accepted | Storage Layout · I/O Pruning |
