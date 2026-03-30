"""BM25 精準匹配索引."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from logsensing.rag.chunker import Chunk


@dataclass
class SearchResult:
    """A search result with score."""

    chunk: Chunk
    score: float


class BM25Index:
    """BM25-based text search index."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._index: object | None = None  # BM25Okapi instance
        self._tokenized: list[list[str]] = []

    def build(self, chunks: list[Chunk]) -> None:
        """Build BM25 index from chunks."""
        from rank_bm25 import BM25Okapi

        self._chunks = list(chunks)
        self._tokenized = [self._tokenize(c.text) for c in chunks]
        self._index = BM25Okapi(self._tokenized) if self._tokenized else None

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search index with query, return top-k results."""
        if self._index is None:
            return []

        tokens = self._tokenize(query)
        scores = self._index.get_scores(tokens)

        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            SearchResult(chunk=self._chunks[idx], score=float(score))
            for idx, score in ranked
            if score > 0
        ]

    def save(self, path: Path) -> None:
        """Save index state (chunks + tokenized corpus) to JSON."""
        data = {
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "source": c.source,
                    "chunk_index": c.chunk_index,
                    "metadata": c.metadata,
                }
                for c in self._chunks
            ],
            "tokenized": self._tokenized,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: Path) -> None:
        """Load index state from JSON and rebuild BM25."""
        from rank_bm25 import BM25Okapi

        data = json.loads(path.read_text(encoding="utf-8"))
        self._chunks = [
            Chunk(
                chunk_id=c["chunk_id"],
                text=c["text"],
                source=c["source"],
                chunk_index=c["chunk_index"],
                metadata=c.get("metadata", {}),
            )
            for c in data["chunks"]
        ]
        self._tokenized = data["tokenized"]
        self._index = BM25Okapi(self._tokenized) if self._tokenized else None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + lowercase tokenizer."""
        return text.lower().split()
