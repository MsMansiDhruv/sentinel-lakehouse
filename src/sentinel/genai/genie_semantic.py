"""Databricks Genie and AI/BI Semantic Layer Compiler with Trusted SQL Catalog."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnAnnotation:
    """Semantic metadata for a table column in Genie and Unity Catalog."""

    name: str
    data_type: str
    description: str
    semantic_role: str = (
        "dimension"  # "primary_key", "foreign_key", "metric", "dimension", "timestamp"
    )
    synonyms: list[str] = field(default_factory=list)
    is_pii: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "description": self.description,
            "semantic_role": self.semantic_role,
            "synonyms": self.synonyms,
            "is_pii": self.is_pii,
        }


@dataclass
class TableAnnotation:
    """Semantic metadata for a Lakehouse table."""

    catalog: str
    schema: str
    table_name: str
    description: str
    columns: list[ColumnAnnotation] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    cluster_by: list[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.table_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "description": self.description,
            "primary_keys": self.primary_keys,
            "cluster_by": self.cluster_by,
            "columns": [col.to_dict() for col in self.columns],
        }


@dataclass
class TableRelationship:
    """Foreign key relationship between two Lakehouse tables."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    relationship_type: str = "many_to_one"  # "one_to_one", "many_to_one", "one_to_many"

    def to_sql_join_clause(self) -> str:
        return (
            f"{self.from_table}.{self.from_column} = {self.to_table}.{self.to_column}"
        )


@dataclass
class TrustedQuery:
    """A verified, gold-standard SQL template for Databricks Genie spaces."""

    query_id: str
    metric_name: str
    description: str
    example_prompts: list[str]
    sql_template: str
    target_tables: list[str] = field(default_factory=list)

    def validate_safety(self) -> bool:
        """Ensure query is strictly read-only and free of destructive DDL/DML."""
        upper = self.sql_template.upper()
        forbidden = [
            "DROP",
            "DELETE",
            "TRUNCATE",
            "ALTER",
            "INSERT",
            "UPDATE",
            "GRANT",
            "REVOKE",
            "CREATE",
            "EXEC",
            "MERGE INTO",
        ]
        for term in forbidden:
            if re.search(r"\b" + term + r"\b", upper):
                raise ValueError(
                    f"Trusted query '{self.query_id}' contains forbidden DDL/DML statement: {term}"
                )
        return True


class GenieSemanticCompiler:
    """Compiles Lakehouse schemas and quality rules into Databricks Genie semantic spaces."""

    def __init__(self, space_name: str, space_description: str) -> None:
        self.space_name = space_name
        self.space_description = space_description
        self._tables: dict[str, TableAnnotation] = {}
        self._relationships: list[TableRelationship] = []
        self._trusted_queries: dict[str, TrustedQuery] = {}

    def register_table(self, table: TableAnnotation) -> None:
        self._tables[table.full_name] = table

    def register_relationship(self, relationship: TableRelationship) -> None:
        self._relationships.append(relationship)

    def register_trusted_query(self, query: TrustedQuery) -> None:
        query.validate_safety()
        self._trusted_queries[query.query_id] = query

    def generate_unity_catalog_comments(self) -> list[str]:
        """Generate DDL statements to persist semantic comments into Unity Catalog."""
        ddl_statements: list[str] = []
        for table in self._tables.values():
            escaped_table_desc = table.description.replace("'", "''")
            ddl_statements.append(
                f"COMMENT ON TABLE {table.full_name} IS '{escaped_table_desc}';"
            )
            for col in table.columns:
                escaped_col_desc = col.description.replace("'", "''")
                ddl_statements.append(
                    f"ALTER TABLE {table.full_name} ALTER COLUMN {col.name} COMMENT '{escaped_col_desc}';"
                )
        return ddl_statements

    def export_genie_space_config(self) -> dict[str, Any]:
        """Export the full semantic schema configuration in Databricks Genie format."""
        return {
            "name": self.space_name,
            "description": self.space_description,
            "version": "1.0",
            "tables": [t.to_dict() for t in self._tables.values()],
            "relationships": [
                {
                    "from_table": rel.from_table,
                    "from_column": rel.from_column,
                    "to_table": rel.to_table,
                    "to_column": rel.to_column,
                    "relationship_type": rel.relationship_type,
                    "join_clause": rel.to_sql_join_clause(),
                }
                for rel in self._relationships
            ],
            "trusted_queries": [
                {
                    "query_id": q.query_id,
                    "metric_name": q.metric_name,
                    "description": q.description,
                    "example_prompts": q.example_prompts,
                    "sql": q.sql_template,
                    "target_tables": q.target_tables,
                }
                for q in self._trusted_queries.values()
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Export serialized Genie space JSON definition."""
        return json.dumps(self.export_genie_space_config(), indent=indent)
