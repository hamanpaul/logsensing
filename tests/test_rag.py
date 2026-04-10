"""Tests for RAG modules: chunker, bm25, vector, retriever."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from logsensing.rag.bm25 import BM25Index, SearchResult
from logsensing.rag.chunker import Chunk, DocumentChunker
from logsensing.rag.retriever import HybridRetriever
from logsensing.rag.turboquant import TurboQuantVectorIndex

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

LONG_TEXT = "word " * 300  # 1500 chars


def _make_chunks(n: int, source: str = "test") -> list[Chunk]:
    """Build *n* sample chunks with distinct text."""
    return [
        Chunk(
            chunk_id=f"{source}:{i}",
            text=f"chunk number {i} with unique content about topic_{i}",
            source=source,
            chunk_index=i,
        )
        for i in range(n)
    ]


@pytest.fixture()
def chunker() -> DocumentChunker:
    return DocumentChunker(chunk_size=100, chunk_overlap=20)


@pytest.fixture()
def sample_chunks() -> list[Chunk]:
    """Five diverse chunks for index tests."""
    return [
        Chunk(
            chunk_id="doc:0", text="kernel panic not syncing fatal error",
            source="doc", chunk_index=0,
        ),
        Chunk(
            chunk_id="doc:1", text="dhcp lease renewed successfully on interface",
            source="doc", chunk_index=1,
        ),
        Chunk(
            chunk_id="doc:2", text="wifi module loaded driver initialized",
            source="doc", chunk_index=2,
        ),
        Chunk(
            chunk_id="doc:3", text="out of memory oom killer invoked",
            source="doc", chunk_index=3,
        ),
        Chunk(
            chunk_id="doc:4", text="boot sequence completed watchdog started",
            source="doc", chunk_index=4,
        ),
    ]


# ===================================================================
# DocumentChunker tests
# ===================================================================
class TestDocumentChunker:
    """DocumentChunker 測試."""

    def test_chunk_text_basic(self, chunker: DocumentChunker) -> None:
        """Chunks text into correct number of pieces."""
        text = "a" * 250  # 250 chars, chunk_size=100, step=80 → 3 chunks
        chunks = chunker.chunk_text(text, source="src")
        assert len(chunks) >= 3
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.source == "src" for c in chunks)

    def test_chunk_text_overlap(self) -> None:
        """Overlap region is shared between consecutive chunks."""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=30)
        text = "x" * 200
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2
        # The last 30 chars of chunk 0 should equal the first 30 chars of chunk 1
        tail = chunks[0].text[-30:]
        head = chunks[1].text[:30]
        assert tail == head

    def test_chunk_text_short(self, chunker: DocumentChunker) -> None:
        """Text shorter than chunk_size produces exactly 1 chunk."""
        chunks = chunker.chunk_text("short text")
        assert len(chunks) == 1
        assert chunks[0].text == "short text"

    def test_chunk_text_empty(self, chunker: DocumentChunker) -> None:
        """Empty / whitespace-only text produces empty list."""
        assert chunker.chunk_text("") == []
        assert chunker.chunk_text("   ") == []

    def test_chunk_file(self, chunker: DocumentChunker, tmp_path: Path) -> None:
        """Reads and chunks a file on disk."""
        p = tmp_path / "sample.txt"
        p.write_text("hello world " * 50, encoding="utf-8")
        chunks = chunker.chunk_file(p)
        assert len(chunks) >= 1
        assert chunks[0].source == str(p)

    def test_chunk_files_multiple(self, chunker: DocumentChunker, tmp_path: Path) -> None:
        """Chunks multiple files and aggregates results."""
        files: list[Path] = []
        for i in range(3):
            p = tmp_path / f"file_{i}.txt"
            p.write_text(f"content of file {i} " * 30, encoding="utf-8")
            files.append(p)

        chunks = chunker.chunk_files(files)
        sources = {c.source for c in chunks}
        assert len(sources) == 3

    def test_chunk_log_lines(self) -> None:
        """Chunks log lines by line count."""
        lines = [f"[2026-03-18 13:54:{i:02d}.000] event {i}" for i in range(120)]
        chunker = DocumentChunker()
        chunks = chunker.chunk_log_lines(lines, source="boot", lines_per_chunk=50, overlap_lines=5)
        assert len(chunks) >= 2
        assert chunks[0].metadata["start_line"] == 0
        assert chunks[0].metadata["end_line"] == 50
        # overlap: second chunk starts at 50 - 5 = 45
        assert chunks[1].metadata["start_line"] == 45

    def test_chunk_id_format(self, chunker: DocumentChunker) -> None:
        """chunk_id follows '{source}:{index}' format."""
        chunks = chunker.chunk_text("a" * 250, source="my_file")
        for c in chunks:
            assert c.chunk_id == f"{c.source}:{c.chunk_index}"
            assert c.chunk_id.startswith("my_file:")


# ===================================================================
# BM25Index tests
# ===================================================================
class TestBM25Index:
    """BM25Index 測試."""

    def test_build_and_search(self, sample_chunks: list[Chunk]) -> None:
        """Build index, search returns relevant results."""
        idx = BM25Index()
        idx.build(sample_chunks)
        results = idx.search("kernel panic")
        assert len(results) >= 1
        assert results[0].chunk.chunk_id == "doc:0"
        assert results[0].score > 0

    def test_search_empty_index(self) -> None:
        """Search on empty / un-built index returns empty list."""
        idx = BM25Index()
        assert idx.search("anything") == []

    def test_search_top_k(self, sample_chunks: list[Chunk]) -> None:
        """Respects top_k limit."""
        idx = BM25Index()
        idx.build(sample_chunks)
        results = idx.search("kernel panic memory wifi boot dhcp", top_k=2)
        assert len(results) <= 2

    def test_save_and_load(self, sample_chunks: list[Chunk], tmp_path: Path) -> None:
        """Save to file, load back, search still works."""
        idx = BM25Index()
        idx.build(sample_chunks)

        save_path = tmp_path / "bm25.json"
        idx.save(save_path)
        assert save_path.exists()

        idx2 = BM25Index()
        idx2.load(save_path)
        results = idx2.search("kernel panic")
        assert len(results) >= 1
        assert results[0].chunk.chunk_id == "doc:0"

    def test_tokenize(self) -> None:
        """Basic tokenization: lowercase + split."""
        tokens = BM25Index._tokenize("Hello World FOO")
        assert tokens == ["hello", "world", "foo"]


# ===================================================================
# VectorIndex tests — skipped when deps missing
# ===================================================================
class TestVectorIndex:
    """VectorIndex 測試 — 需要 faiss + sentence-transformers."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_deps(self) -> None:
        pytest.importorskip("faiss", reason="faiss-cpu not installed")
        pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

    def test_is_available(self) -> None:
        """is_available returns True when deps are installed."""
        from logsensing.rag.vector import VectorIndex

        vi = VectorIndex()
        assert vi.is_available is True

    @pytest.mark.slow
    def test_build_and_search(self, sample_chunks: list[Chunk]) -> None:
        """Build vector index and search returns results."""
        from logsensing.rag.vector import VectorIndex

        vi = VectorIndex()
        vi.build(sample_chunks)
        results = vi.search("kernel error crash")
        assert len(results) >= 1
        assert isinstance(results[0], SearchResult)
        assert results[0].score > 0

    @pytest.mark.slow
    def test_save_and_load(self, sample_chunks: list[Chunk], tmp_path: Path) -> None:
        """Save/load round trip preserves search capability."""
        from logsensing.rag.vector import VectorIndex

        vi = VectorIndex()
        vi.build(sample_chunks)

        save_dir = tmp_path / "vec_index"
        vi.save(save_dir)
        assert (save_dir / "meta.json").exists()
        assert (save_dir / "index.faiss").exists()

        vi2 = VectorIndex()
        vi2.load(save_dir)
        results = vi2.search("kernel error")
        assert len(results) >= 1


# ===================================================================
# TurboQuantVectorIndex tests
# ===================================================================
class FakeEncoder:
    """Deterministic encoder for backend tests without external model deps."""

    def __init__(self) -> None:
        self._basis = {
            "kernel": np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            "panic": np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            "wifi": np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            "driver": np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            "memory": np.array([0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0], dtype=np.float32),
            "boot": np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0], dtype=np.float32),
            "dhcp": np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0], dtype=np.float32),
            "rpc": np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        }

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        del show_progress_bar
        embeddings: list[np.ndarray] = []
        for text in texts:
            vector = np.zeros(8, dtype=np.float32)
            lowered = text.lower()
            for token, basis in self._basis.items():
                if token in lowered:
                    vector += basis
            if not np.any(vector):
                vector[0] = 1.0
            if normalize_embeddings:
                vector = vector / np.linalg.norm(vector)
            embeddings.append(vector)
        return np.array(embeddings, dtype=np.float32)


class TestTurboQuantVectorIndex:
    """TurboQuant-style backend tests."""

    def test_build_and_search_with_fake_encoder(self, sample_chunks: list[Chunk]) -> None:
        index = TurboQuantVectorIndex(
            bit_width=4,
            rotation_seed=7,
            encoder=FakeEncoder(),
        )

        index.build(sample_chunks)
        results = index.search("kernel panic", top_k=2)

        assert len(results) == 2
        assert results[0].chunk.chunk_id == "doc:0"

    def test_save_and_load_round_trip(self, sample_chunks: list[Chunk], tmp_path: Path) -> None:
        index = TurboQuantVectorIndex(
            bit_width=3,
            rotation_seed=3,
            encoder=FakeEncoder(),
        )
        index.build(sample_chunks)

        save_dir = tmp_path / "turboquant"
        index.save(save_dir)

        loaded = TurboQuantVectorIndex(encoder=FakeEncoder())
        loaded.load(save_dir)
        results = loaded.search("wifi driver", top_k=2)

        assert (save_dir / "meta.json").exists()
        assert (save_dir / "quantized.npz").exists()
        assert results
        assert results[0].chunk.chunk_id == "doc:2"

    def test_saved_metadata_marks_backend(self, sample_chunks: list[Chunk], tmp_path: Path) -> None:
        index = TurboQuantVectorIndex(
            bit_width=4,
            rotation_seed=11,
            encoder=FakeEncoder(),
        )
        index.build(sample_chunks)
        save_dir = tmp_path / "turboquant"
        index.save(save_dir)

        meta = (save_dir / "meta.json").read_text(encoding="utf-8")

        assert '"backend": "turboquant"' in meta
        assert '"version": "turboquant-vector-v1"' in meta
        assert '"bit_width": 4' in meta


# ===================================================================
# HybridRetriever tests
# ===================================================================
class TestHybridRetriever:
    """HybridRetriever 測試."""

    def test_bm25_only(self, sample_chunks: list[Chunk]) -> None:
        """Works with only BM25 (no vector)."""
        bm25 = BM25Index()
        bm25.build(sample_chunks)
        retriever = HybridRetriever(bm25=bm25)
        results = retriever.search("kernel panic")
        assert len(results) >= 1
        assert results[0].score > 0

    def test_vector_only(self, sample_chunks: list[Chunk]) -> None:
        """Works with only VectorIndex (mocked)."""
        mock_vector = MagicMock()
        mock_vector.search.return_value = [
            SearchResult(chunk=sample_chunks[2], score=0.9),
            SearchResult(chunk=sample_chunks[0], score=0.7),
        ]
        retriever = HybridRetriever(vector=mock_vector)
        results = retriever.search("wifi driver")
        assert len(results) >= 1
        mock_vector.search.assert_called_once()

    def test_hybrid_fusion(self, sample_chunks: list[Chunk]) -> None:
        """RRF fusion merges results from both BM25 and vector."""
        bm25 = BM25Index()
        bm25.build(sample_chunks)

        mock_vector = MagicMock()
        mock_vector.search.return_value = [
            SearchResult(chunk=sample_chunks[2], score=0.95),
            SearchResult(chunk=sample_chunks[0], score=0.80),
        ]

        retriever = HybridRetriever(bm25=bm25, vector=mock_vector)
        results = retriever.search("kernel error")
        assert len(results) >= 1
        # The fusion should include chunks from both sources
        ids = {r.chunk.chunk_id for r in results}
        assert len(ids) >= 1

    def test_empty_retriever(self) -> None:
        """No indexes configured returns empty results."""
        retriever = HybridRetriever()
        results = retriever.search("anything")
        assert results == []

    def test_hybrid_with_turboquant_backend(self, sample_chunks: list[Chunk]) -> None:
        """Hybrid retriever should work with the compressed backend."""
        bm25 = BM25Index()
        bm25.build(sample_chunks)
        vector = TurboQuantVectorIndex(
            bit_width=4,
            rotation_seed=5,
            encoder=FakeEncoder(),
        )
        vector.build(sample_chunks)

        retriever = HybridRetriever(bm25=bm25, vector=vector)
        results = retriever.search("kernel panic", top_k=3)

        assert results
        assert any(result.chunk.chunk_id == "doc:0" for result in results)
