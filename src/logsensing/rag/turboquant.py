"""Paper-derived TurboQuant-style vector index.

This implementation intentionally uses only public paper concepts:
- random sign flips
- orthonormal Walsh-Hadamard rotation
- low-bit scalar quantization on rotated vectors

It does not copy or vendor GPL repository code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from logsensing.rag.bm25 import SearchResult
from logsensing.rag.chunker import Chunk


class TurboQuantVectorIndex:
    """Compressed vector index using a paper-derived TurboQuant-style backend."""

    backend_name = "turboquant"
    format_version = "turboquant-vector-v1"

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        *,
        bit_width: int = 4,
        rotation_seed: int = 0,
        encoder: Any | None = None,
    ) -> None:
        self._model_name = model_name
        self._bit_width = max(2, min(bit_width, 8))
        self._rotation_seed = rotation_seed
        self._encoder: Any | None = encoder
        self._chunks: list[Chunk] = []
        self._dimension = 0
        self._padded_dimension = 0
        self._codes: NDArray[np.int16] | None = None
        self._scales: NDArray[np.float32] | None = None
        self._signs: NDArray[np.float32] | None = None

    def build(self, chunks: list[Chunk]) -> None:
        """Build compressed index from chunks."""
        self._chunks = list(chunks)
        if not self._chunks:
            self._dimension = 0
            self._padded_dimension = 0
            self._codes = None
            self._scales = None
            self._signs = None
            return

        embeddings = self._encode([chunk.text for chunk in self._chunks])
        self._dimension = int(embeddings.shape[1])
        self._padded_dimension = _next_power_of_two(self._dimension)
        self._signs = self._make_signs(self._padded_dimension)
        rotated = self._rotate(embeddings)
        self._codes, self._scales = self._quantize(rotated)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search using rotated-query vs dequantized-rotated-vector inner product."""
        if self._codes is None or self._scales is None or self._signs is None:
            return []

        query_embedding = self._encode([query])
        rotated_query = self._rotate(query_embedding)[0]
        reconstructed = self._dequantize()
        scores = reconstructed @ rotated_query
        ranked = np.argsort(scores)[::-1][: min(top_k, len(self._chunks))]
        return [
            SearchResult(chunk=self._chunks[int(idx)], score=float(scores[int(idx)]))
            for idx in ranked
        ]

    def save(self, path: Path) -> None:
        """Save compressed vectors and metadata to disk."""
        path.mkdir(parents=True, exist_ok=True)
        meta = {
            "backend": self.backend_name,
            "version": self.format_version,
            "model_name": self._model_name,
            "bit_width": self._bit_width,
            "rotation_seed": self._rotation_seed,
            "dimension": self._dimension,
            "padded_dimension": self._padded_dimension,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "source": chunk.source,
                    "chunk_index": chunk.chunk_index,
                    "metadata": chunk.metadata,
                }
                for chunk in self._chunks
            ],
        }
        (path / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if self._codes is not None and self._scales is not None and self._signs is not None:
            np.savez_compressed(
                path / "quantized.npz",
                codes=self._codes,
                scales=self._scales,
                signs=self._signs,
            )

    def load(self, path: Path) -> None:
        """Load compressed vectors and metadata from disk."""
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        if meta.get("backend") != self.backend_name:
            raise ValueError(f"Unsupported backend: {meta.get('backend')}")
        if meta.get("version") != self.format_version:
            raise ValueError(f"Unsupported metadata version: {meta.get('version')}")

        self._model_name = str(meta["model_name"])
        self._bit_width = int(meta["bit_width"])
        self._rotation_seed = int(meta["rotation_seed"])
        self._dimension = int(meta["dimension"])
        self._padded_dimension = int(meta["padded_dimension"])
        self._chunks = [
            Chunk(
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
                source=chunk["source"],
                chunk_index=chunk["chunk_index"],
                metadata=chunk.get("metadata", {}),
            )
            for chunk in meta["chunks"]
        ]

        data = np.load(path / "quantized.npz")
        self._codes = np.asarray(data["codes"], dtype=np.int16)
        self._scales = np.asarray(data["scales"], dtype=np.float32)
        self._signs = np.asarray(data["signs"], dtype=np.float32)

    @property
    def is_available(self) -> bool:
        """Check whether an encoder is available for build/search."""
        if self._encoder is not None:
            return True
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def _encode(self, texts: list[str]) -> NDArray[np.float32]:
        encoder = self._get_encoder()
        embeddings = encoder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def _get_encoder(self) -> Any:
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(self._model_name)
        return self._encoder

    def _rotate(self, vectors: NDArray[np.float32]) -> NDArray[np.float32]:
        if self._signs is None:
            raise ValueError("Rotation signs are not initialized")

        batch_size = int(vectors.shape[0])
        padded = np.zeros((batch_size, self._padded_dimension), dtype=np.float32)
        padded[:, : self._dimension] = vectors
        signed = padded * self._signs
        return _fwht_batch(signed)

    def _quantize(
        self,
        rotated: NDArray[np.float32],
    ) -> tuple[NDArray[np.int16], NDArray[np.float32]]:
        levels = max(1, (2 ** (self._bit_width - 1)) - 1)
        max_abs = np.max(np.abs(rotated), axis=1)
        scales = np.where(max_abs > 0, max_abs / levels, 1.0).astype(np.float32)
        codes = np.rint(rotated / scales[:, None])
        codes = np.clip(codes, -levels, levels).astype(np.int16)
        return codes, scales

    def _dequantize(self) -> NDArray[np.float32]:
        if self._codes is None or self._scales is None:
            raise ValueError("Compressed vectors are not initialized")
        return self._codes.astype(np.float32) * self._scales[:, None]

    def _make_signs(self, dimension: int) -> NDArray[np.float32]:
        rng = np.random.default_rng(self._rotation_seed)
        random_bits = rng.integers(0, 2, size=dimension, dtype=np.int8)
        return np.where(random_bits == 0, -1.0, 1.0).astype(np.float32)


def _next_power_of_two(value: int) -> int:
    if value <= 1:
        return 1
    return 1 << (value - 1).bit_length()


def _fwht_batch(vectors: NDArray[np.float32]) -> NDArray[np.float32]:
    output = np.asarray(vectors, dtype=np.float32).copy()
    width = int(output.shape[1])
    step = 1
    while step < width:
        jump = step * 2
        for start in range(0, width, jump):
            left = output[:, start : start + step].copy()
            right = output[:, start + step : start + jump].copy()
            output[:, start : start + step] = left + right
            output[:, start + step : start + jump] = left - right
        step = jump
    scale = np.float32(np.sqrt(width))
    normalized: NDArray[np.float32] = np.asarray(output / scale, dtype=np.float32)
    return normalized
