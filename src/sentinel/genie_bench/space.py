"""Semantic layer compiler and Unity Catalog synchronization for Databricks Genie spaces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenieDimension:
    """A dimension column in the Genie semantic space."""

    column_name: str
    data_type: str
    description: str
    synonyms: list[str] = field(default_factory=list)
    sample_values: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "data_type": self.data_type,
            "description": self.description,
            "synonyms": self.synonyms,
            "sample_values": self.sample_values,
        }


@dataclass
class GenieMeasure:
    """A pre-calculated metric or aggregation in the Genie semantic space."""

    name: str
    expression: str
    description: str
    synonyms: list[str] = field(default_factory=list)
    format_type: str = "number"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expression": self.expression,
            "description": self.description,
            "synonyms": self.synonyms,
            "format_type": self.format_type,
        }


@dataclass
class GenieJoin:
    """Relationship mapping between tables in the semantic space."""

    from_table: str
    to_table: str
    join_type: str
    on_clause: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_table": self.from_table,
            "to_table": self.to_table,
            "join_type": self.join_type,
            "on_clause": self.on_clause,
        }


@dataclass
class GenieTable:
    """A table registered in Databricks Unity Catalog semantic space."""

    catalog: str
    schema: str
    table_name: str
    description: str
    dimensions: list[GenieDimension] = field(default_factory=list)
    measures: list[GenieMeasure] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.table_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog": self.catalog,
            "schema": self.schema,
            "table_name": self.table_name,
            "full_name": self.full_name,
            "description": self.description,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "measures": [m.to_dict() for m in self.measures],
        }


@dataclass
class GenieSpace:
    """A complete Databricks AI/BI Genie Space configuration."""

    space_id: str
    name: str
    description: str
    tables: list[GenieTable] = field(default_factory=list)
    joins: list[GenieJoin] = field(default_factory=list)
    curated_instructions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "name": self.name,
            "description": self.description,
            "tables": [t.to_dict() for t in self.tables],
            "joins": [j.to_dict() for j in self.joins],
            "curated_instructions": self.curated_instructions,
        }

    def to_json(self, indent: int = 2) -> str:
        """Export Genie Space config as JSON payload for Databricks AI/BI API."""
        return json.dumps(self.to_dict(), indent=indent)

    def generate_unity_catalog_ddl(self) -> list[str]:
        """Generate idempotent COMMENT ON TABLE/COLUMN DDL statements for Unity Catalog."""
        ddl_statements: list[str] = []
        for table in self.tables:
            # Escape single quotes in comments
            table_desc = table.description.replace("'", "''")
            ddl_statements.append(
                f"COMMENT ON TABLE {table.full_name} IS '{table_desc}';"
            )
            for dim in table.dimensions:
                dim_desc = dim.description.replace("'", "''")
                if dim.synonyms:
                    dim_desc += f" (Synonyms: {', '.join(dim.synonyms)})"
                ddl_statements.append(
                    f"COMMENT ON COLUMN {table.full_name}.{dim.column_name} IS '{dim_desc}';"
                )
        return ddl_statements
