"""Structure-aware document chunking for enterprise governance assets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentChunk:
    """A semantic chunk of an enterprise document."""

    chunk_id: str
    doc_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert chunk to a serializable dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "content": self.content,
            "metadata": self.metadata,
        }


class StructureAwareChunker:
    """Chunks documents while preserving structural elements like tables and code blocks."""

    def __init__(
        self,
        max_chunk_chars: int = 1000,
        overlap_chars: int = 150,
        preserve_tables: bool = True,
        preserve_code_blocks: bool = True,
    ) -> None:
        if max_chunk_chars <= overlap_chars:
            raise ValueError(
                "max_chunk_chars must be strictly greater than overlap_chars."
            )
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars
        self.preserve_tables = preserve_tables
        self.preserve_code_blocks = preserve_code_blocks

    def chunk_document(
        self,
        doc_id: str,
        text: str,
        doc_metadata: dict[str, Any] | None = None,
    ) -> list[DocumentChunk]:
        """Split document into structure-aware semantic chunks."""
        base_meta = dict(doc_metadata or {})
        base_meta.setdefault("doc_id", doc_id)

        blocks = self._parse_blocks(text)
        if not blocks:
            return []

        chunks: list[DocumentChunk] = []
        current_content: list[str] = []
        current_len = 0
        current_meta: dict[str, Any] = dict(base_meta)
        chunk_idx = 0

        for block_type, block_text, section_header in blocks:
            block_len = len(block_text)

            # If a single table or code block exceeds max_chunk_chars, we preserve it as a single chunk
            if block_type in ("table", "code") and block_len > self.max_chunk_chars:
                if current_content:
                    combined = "\n\n".join(current_content).strip()
                    if combined:
                        chunks.append(
                            self._create_chunk(
                                doc_id, chunk_idx, combined, current_meta
                            )
                        )
                        chunk_idx += 1
                        current_content = []
                        current_len = 0

                block_meta = dict(base_meta)
                block_meta["section"] = section_header
                block_meta["is_" + block_type] = True
                chunks.append(
                    self._create_chunk(
                        doc_id, chunk_idx, block_text.strip(), block_meta
                    )
                )
                chunk_idx += 1
                continue

            if current_len + block_len > self.max_chunk_chars and current_content:
                combined = "\n\n".join(current_content).strip()
                if combined:
                    chunks.append(
                        self._create_chunk(doc_id, chunk_idx, combined, current_meta)
                    )
                    chunk_idx += 1

                # Sliding window overlap
                if self.overlap_chars > 0 and current_content:
                    overlap_seed = current_content[-1]
                    if len(overlap_seed) > self.overlap_chars:
                        overlap_seed = overlap_seed[-self.overlap_chars :]
                    current_content = [overlap_seed, block_text]
                    current_len = len(overlap_seed) + block_len
                else:
                    current_content = [block_text]
                    current_len = block_len

                current_meta = dict(base_meta)
                if section_header:
                    current_meta["section"] = section_header
            else:
                current_content.append(block_text)
                current_len += block_len
                if section_header and "section" not in current_meta:
                    current_meta["section"] = section_header

        if current_content:
            combined = "\n\n".join(current_content).strip()
            if combined:
                chunks.append(
                    self._create_chunk(doc_id, chunk_idx, combined, current_meta)
                )

        return chunks

    def _create_chunk(
        self,
        doc_id: str,
        index: int,
        content: str,
        metadata: dict[str, Any],
    ) -> DocumentChunk:
        content_hash = hashlib.sha256(
            f"{doc_id}:{index}:{content}".encode()
        ).hexdigest()[:12]
        chunk_id = f"{doc_id}-chk-{index:03d}-{content_hash}"
        meta = dict(metadata)
        meta["chunk_index"] = index
        meta["char_length"] = len(content)
        return DocumentChunk(
            chunk_id=chunk_id, doc_id=doc_id, content=content, metadata=meta
        )

    def _parse_blocks(self, text: str) -> list[tuple[str, str, str]]:
        """Parse text into typed blocks: ('heading' | 'table' | 'code' | 'paragraph', content, active_section)."""
        lines = text.splitlines()
        blocks: list[tuple[str, str, str]] = []

        i = 0
        active_section = "General"
        n = len(lines)

        while i < n:
            line = lines[i]

            # Section heading
            if line.startswith("#"):
                active_section = line.lstrip("#").strip()
                blocks.append(("heading", line, active_section))
                i += 1
                continue

            # Code block
            if line.strip().startswith("```"):
                code_lines = [line]
                i += 1
                while i < n and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if i < n:
                    code_lines.append(lines[i])
                    i += 1
                blocks.append(("code", "\n".join(code_lines), active_section))
                continue

            # Markdown Table detection
            if line.strip().startswith("|") and line.strip().endswith("|"):
                table_lines = [line]
                i += 1
                while (
                    i < n
                    and lines[i].strip().startswith("|")
                    and lines[i].strip().endswith("|")
                ):
                    table_lines.append(lines[i])
                    i += 1
                blocks.append(("table", "\n".join(table_lines), active_section))
                continue

            # Standard paragraph
            if not line.strip():
                i += 1
                continue

            para_lines = [line]
            i += 1
            while (
                i < n
                and lines[i].strip()
                and not lines[i].startswith("#")
                and not lines[i].strip().startswith("```")
                and not (
                    lines[i].strip().startswith("|") and lines[i].strip().endswith("|")
                )
            ):
                para_lines.append(lines[i])
                i += 1
            blocks.append(("paragraph", "\n".join(para_lines), active_section))

        return blocks
