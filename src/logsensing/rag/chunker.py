"""文件切塊器 — 將文件切割為可檢索的文字區塊."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Chunk:
    """A text chunk with metadata."""

    chunk_id: str  # unique id: "{source}:{chunk_index}"
    text: str  # chunk content
    source: str  # source file path or identifier
    chunk_index: int  # position within the document
    metadata: dict[str, Any] = field(default_factory=dict)  # extra metadata


class DocumentChunker:
    """Split documents into overlapping text chunks."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(
        self,
        text: str,
        source: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Split text into overlapping chunks by character count."""
        if not text.strip():
            return []

        chunks: list[Chunk] = []
        base_metadata = dict(metadata or {})
        step = max(self.chunk_size - self.chunk_overlap, 1)
        start = 0
        idx = 0

        while start < len(text):
            end = start + self.chunk_size
            segment = text[start:end]
            if segment.strip():
                chunks.append(
                    Chunk(
                        chunk_id=f"{source}:{idx}",
                        text=segment,
                        source=source,
                        chunk_index=idx,
                        metadata=dict(base_metadata),
                    )
                )
                idx += 1
            start += step

        return chunks

    def chunk_file(
        self,
        path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Read and chunk a text file (markdown, txt, etc.)."""
        text = path.read_text(encoding="utf-8")
        return self.chunk_text(text, source=str(path), metadata=metadata)

    def chunk_files(
        self,
        paths: list[Path],
        metadata_by_path: dict[str, dict[str, Any]] | None = None,
    ) -> list[Chunk]:
        """Chunk multiple files."""
        chunks: list[Chunk] = []
        for p in paths:
            metadata = None
            if metadata_by_path is not None:
                metadata = metadata_by_path.get(str(p.resolve())) or metadata_by_path.get(str(p))
            chunks.extend(self.chunk_file(p, metadata=metadata))
        return chunks

    def chunk_log_lines(
        self,
        lines: list[str],
        source: str = "log",
        lines_per_chunk: int = 50,
        overlap_lines: int = 5,
    ) -> list[Chunk]:
        """Chunk log lines by line count instead of character count.

        This is useful for indexing log files for retrieval.
        """
        if not lines:
            return []

        chunks: list[Chunk] = []
        step = max(lines_per_chunk - overlap_lines, 1)
        start = 0
        idx = 0

        while start < len(lines):
            end = min(start + lines_per_chunk, len(lines))
            segment = "\n".join(lines[start:end])
            if segment.strip():
                chunks.append(
                    Chunk(
                        chunk_id=f"{source}:{idx}",
                        text=segment,
                        source=source,
                        chunk_index=idx,
                        metadata={"start_line": start, "end_line": end},
                    )
                )
                idx += 1
            start += step

        return chunks
