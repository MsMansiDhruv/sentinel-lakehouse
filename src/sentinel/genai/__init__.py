"""Sentinel-GenAI: Enterprise Hybrid RAG and Genie Semantic Engine."""

from sentinel.genai.chunker import DocumentChunk, StructureAwareChunker
from sentinel.genai.compound_router import (
    CompoundQueryRouter,
    CompoundResponse,
    QueryIntent,
)
from sentinel.genai.embeddings import (
    DatabricksEmbeddings,
    EmbeddingProvider,
    LocalDeterministicEmbeddings,
)
from sentinel.genai.evaluator import BenchmarkScorecard, EvalTestCase, GenAIEvaluator
from sentinel.genai.genie_semantic import (
    ColumnAnnotation,
    GenieSemanticCompiler,
    TableAnnotation,
    TableRelationship,
    TrustedQuery,
)
from sentinel.genai.vector_search import HybridVectorIndex, SearchResult

__all__ = [
    "DocumentChunk",
    "StructureAwareChunker",
    "EmbeddingProvider",
    "DatabricksEmbeddings",
    "LocalDeterministicEmbeddings",
    "HybridVectorIndex",
    "SearchResult",
    "ColumnAnnotation",
    "TableAnnotation",
    "TableRelationship",
    "TrustedQuery",
    "GenieSemanticCompiler",
    "QueryIntent",
    "CompoundResponse",
    "CompoundQueryRouter",
    "EvalTestCase",
    "BenchmarkScorecard",
    "GenAIEvaluator",
]
