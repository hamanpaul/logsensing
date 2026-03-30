"""混合檢索 API — 融合 BM25 與向量檢索."""

from __future__ import annotations

from logsensing.rag.bm25 import BM25Index, SearchResult
from logsensing.rag.chunker import Chunk
from logsensing.rag.vector import VectorIndex


class HybridRetriever:
    """Hybrid retriever using RRF (Reciprocal Rank Fusion)."""

    def __init__(
        self,
        bm25: BM25Index | None = None,
        vector: VectorIndex | None = None,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
        rrf_k: int = 60,
    ):
        self._bm25 = bm25
        self._vector = vector
        self._bm25_weight = bm25_weight
        self._vector_weight = vector_weight
        self._rrf_k = rrf_k

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search with RRF fusion of BM25 and vector results."""
        bm25_results = (
            self._bm25.search(query, top_k=top_k * 2) if self._bm25 else []
        )
        vector_results = (
            self._vector.search(query, top_k=top_k * 2) if self._vector else []
        )
        return self._rrf_fuse(bm25_results, vector_results, top_k)

    def _rrf_fuse(
        self,
        bm25_results: list[SearchResult],
        vector_results: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion."""
        scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}

        for rank, r in enumerate(bm25_results):
            cid = r.chunk.chunk_id
            scores[cid] = scores.get(cid, 0) + self._bm25_weight / (
                self._rrf_k + rank + 1
            )
            chunk_map[cid] = r.chunk

        for rank, r in enumerate(vector_results):
            cid = r.chunk.chunk_id
            scores[cid] = scores.get(cid, 0) + self._vector_weight / (
                self._rrf_k + rank + 1
            )
            chunk_map[cid] = r.chunk

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:top_k]
        return [
            SearchResult(chunk=chunk_map[cid], score=scores[cid])
            for cid in sorted_ids
        ]
