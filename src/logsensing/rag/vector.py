"""FAISS 向量檢索索引."""

from __future__ import annotations

import json
from pathlib import Path

from logsensing.rag.bm25 import SearchResult
from logsensing.rag.chunker import Chunk


class VectorIndex:
    """FAISS-based vector search index."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._chunks: list[Chunk] = []
        self._index: object | None = None  # faiss.IndexFlatIP
        self._model: object | None = None  # SentenceTransformer
        self._dimension: int = 0

    def build(self, chunks: list[Chunk]) -> None:
        """Build FAISS index from chunks."""
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self._model_name)
        self._chunks = list(chunks)
        texts = [c.text for c in chunks]
        embeddings = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        embeddings = np.array(embeddings, dtype="float32")
        self._dimension = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(self._dimension)
        self._index.add(embeddings)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search index with query vector, return top-k results."""
        if self._index is None or self._model is None:
            return []
        import numpy as np

        qvec = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )
        qvec = np.array(qvec, dtype="float32")
        scores, indices = self._index.search(qvec, min(top_k, len(self._chunks)))
        results: list[SearchResult] = []
        for score, idx in zip(scores[0], indices[0], strict=True):
            if idx < 0:
                continue
            results.append(
                SearchResult(chunk=self._chunks[int(idx)], score=float(score))
            )
        return results

    def save(self, path: Path) -> None:
        """Save FAISS index and chunk metadata to disk."""
        import faiss

        path.mkdir(parents=True, exist_ok=True)
        meta = {
            "model_name": self._model_name,
            "dimension": self._dimension,
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
        }
        (path / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if self._index is not None:
            faiss.write_index(self._index, str(path / "index.faiss"))

    def load(self, path: Path) -> None:
        """Load FAISS index and chunk metadata from disk."""
        import faiss
        from sentence_transformers import SentenceTransformer

        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        self._model_name = meta["model_name"]
        self._dimension = meta["dimension"]
        self._chunks = [
            Chunk(
                chunk_id=c["chunk_id"],
                text=c["text"],
                source=c["source"],
                chunk_index=c["chunk_index"],
                metadata=c.get("metadata", {}),
            )
            for c in meta["chunks"]
        ]
        self._model = SentenceTransformer(self._model_name)
        self._index = faiss.read_index(str(path / "index.faiss"))

    @property
    def is_available(self) -> bool:
        """Check if FAISS + sentence-transformers are available."""
        try:
            import faiss  # noqa: F401
            import sentence_transformers  # noqa: F401
        except ImportError:
            return False
        return True
