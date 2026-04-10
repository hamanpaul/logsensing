"""LogSensing 組態管理."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

if sys.version_info >= (3, 11):
    import tomllib as toml_loader
else:
    import tomli as toml_loader  # type: ignore[import-not-found]


class ParserConfig(BaseModel):
    """Parser 階段組態."""

    anchors: list[str] = Field(default=["U-Boot TPL"])
    fallback_anchors: list[str] = Field(default=["Starting kernel", "Booting Linux"])
    timestamp_pattern: str = Field(
        default=r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] "
    )
    encoding: str = "utf-8"
    max_cycle_lines: int = 100_000
    aaak_enabled: bool = False
    aaak_entity_map: dict[str, str] = Field(default_factory=dict)
    aaak_max_summary_items: int = 5


class DrainConfig(BaseModel):
    """Drain3 組態."""

    sim_th: float = 0.4
    depth: int = 4
    max_clusters: int = 1024
    extra_delimiters: list[str] = Field(default=[":", "=", "|"])


class AnalyzerConfig(BaseModel):
    """Analyzer 階段組態."""

    context_lines_before: int = 50
    context_lines_after: int = 50
    timeout_sigma: float = 3.0


class AgentConfig(BaseModel):
    """Agent 組態."""

    model: str = "gpt-4o"
    api_base: str = ""
    temperature: float = 0.1
    max_tokens: int = 4096


class RagConfig(BaseModel):
    """RAG 組態."""

    chunk_size: int = 512
    chunk_overlap: int = 64
    index_root: str = ".cache/logsensing/rag"
    bm25_index_path: str = ""
    faiss_index_path: str = ""
    knowledge_docs: list[str] = Field(default_factory=list)
    platform_docs: dict[str, list[str]] = Field(default_factory=dict)
    auto_writeback: bool = True
    prefer_compact_experience: bool = False
    vector_backend: str = "faiss"
    vector_compression_bits: int = 4
    vector_rotation_seed: int = 0


class AppConfig(BaseModel):
    """應用程式頂層組態."""

    platform: str = Field(default="auto", description="平台名稱: auto, bdk, prplos")
    parser: ParserConfig = Field(default_factory=ParserConfig)
    drain: DrainConfig = Field(default_factory=DrainConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    rag: RagConfig = Field(default_factory=RagConfig)

    @classmethod
    def from_toml(cls, path: Path) -> AppConfig:
        """從 TOML 檔案載入組態."""
        with open(path, "rb") as f:
            data = toml_loader.load(f)
        return cls(**data)
