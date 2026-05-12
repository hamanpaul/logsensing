"""LogSensing CLI 入口."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from logsensing.config import AppConfig

if TYPE_CHECKING:
    from logsensing.parser.drain import DrainParser
    from logsensing.parser.splitter import StreamSplitter
    from logsensing.platform.base import PlatformProfile
    from logsensing.rag.chunker import Chunk
    from logsensing.rag.retriever import HybridRetriever, VectorSearchBackend

app = typer.Typer(name="logsensing", help="系統日誌自動化分析與 AI 診斷工具", no_args_is_help=True)
console = Console()

# Sub-command groups
train_app = typer.Typer(help="訓練模型")
agent_app = typer.Typer(help="AI Agent 功能")
app.add_typer(train_app, name="train")
app.add_typer(agent_app, name="agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_config(config_path: Path | None) -> AppConfig:
    """載入組態，若無指定則使用預設值."""
    if config_path is not None:
        if not config_path.exists():
            console.print(f"[red]錯誤: 組態檔 {config_path} 不存在[/red]")
            raise typer.Exit(code=1)
        return AppConfig.from_toml(config_path)
    return AppConfig()


def _resolve_platform(
    platform_name: str | None,
    logfile: Path | None = None,
    cfg: AppConfig | None = None,
) -> PlatformProfile:
    """解析平台 profile."""
    from logsensing.platform.registry import resolve_platform

    name = platform_name
    if not name and cfg:
        name = cfg.platform
    return resolve_platform(name, logfile)


def _build_splitter(
    cfg: AppConfig,
    anchors: list[str] | None = None,
    platform: PlatformProfile | None = None,
) -> StreamSplitter:
    """建立 StreamSplitter."""
    from logsensing.parser.splitter import StreamSplitter

    if platform is not None:
        return StreamSplitter.from_platform(platform, max_cycle_lines=cfg.parser.max_cycle_lines)
    return StreamSplitter(
        anchors=anchors or cfg.parser.anchors,
        fallback_anchors=cfg.parser.fallback_anchors,
        max_cycle_lines=cfg.parser.max_cycle_lines,
        timestamp_pattern=cfg.parser.timestamp_pattern,
    )


def _build_drain(cfg: AppConfig) -> DrainParser:
    """建立 DrainParser."""
    from logsensing.parser.drain import DrainParser

    return DrainParser(
        sim_th=cfg.drain.sim_th,
        depth=cfg.drain.depth,
        max_clusters=cfg.drain.max_clusters,
        extra_delimiters=cfg.drain.extra_delimiters,
    )


def _validate_logfile(logfile: Path) -> None:
    """確認日誌檔案存在."""
    if not logfile.exists():
        console.print(f"[red]錯誤: 日誌檔案 {logfile} 不存在[/red]")
        raise typer.Exit(code=1)


def _resolve_rag_platform(
    cfg: AppConfig,
    platform_name: str | None,
    logfile: Path | None,
) -> PlatformProfile | None:
    """Resolve platform for RAG when enough context is available."""
    effective_name = platform_name or cfg.platform
    if logfile is not None and logfile.exists():
        return _resolve_platform(effective_name, logfile, cfg)
    if effective_name and effective_name != "auto":
        return _resolve_platform(effective_name, None, cfg)
    return None


def _resolve_knowledge_docs(
    cfg: AppConfig,
    knowledge_docs: list[Path] | None,
    *,
    platform_name: str | None = None,
) -> list[Path]:
    """解析知識庫文件路徑."""
    raw_docs = [Path(p) for p in cfg.rag.knowledge_docs]
    if platform_name:
        raw_docs.extend(Path(p) for p in cfg.rag.platform_docs.get(platform_name, []))
    if knowledge_docs:
        raw_docs.extend(knowledge_docs)
    resolved_docs: list[Path] = []
    seen: set[str] = set()

    for doc in raw_docs:
        doc_path = doc.expanduser()
        if not doc_path.exists():
            console.print(f"[red]錯誤: 知識庫文件 {doc_path} 不存在[/red]")
            raise typer.Exit(code=1)
        if not doc_path.is_file():
            console.print(f"[red]錯誤: 知識庫路徑 {doc_path} 不是檔案[/red]")
            raise typer.Exit(code=1)

        resolved = doc_path.resolve()
        resolved_key = str(resolved)
        if resolved_key not in seen:
            resolved_docs.append(resolved)
            seen.add(resolved_key)

    return resolved_docs


def _resolve_rag_index_path(cli_path: Path | None, config_value: str) -> Path | None:
    """解析 RAG 索引路徑，CLI 優先於 config."""
    if cli_path is not None:
        return cli_path.expanduser()
    if config_value:
        return Path(config_value).expanduser()
    return None


def _chunk_knowledge_docs(
    cfg: AppConfig,
    doc_paths: list[Path],
    *,
    platform_name: str | None = None,
    experience_paths: list[Path] | None = None,
) -> list[Chunk]:
    """將知識庫文件切塊."""
    from logsensing.rag.chunker import DocumentChunker

    chunker = DocumentChunker(
        chunk_size=cfg.rag.chunk_size,
        chunk_overlap=cfg.rag.chunk_overlap,
    )
    chunks = []
    experience_keys = {
        str(path.resolve()) for path in (experience_paths or []) if path.exists()
    }
    for doc_path in doc_paths:
        resolved_key = str(doc_path.resolve())
        source_type = "experience" if resolved_key in experience_keys else "doc"
        chunks.extend(
            chunker.chunk_file(
                doc_path,
                metadata={
                    "platform": platform_name or "",
                    "source_type": source_type,
                },
            )
        )
    return chunks


def _build_rag_retriever(
    cfg: AppConfig,
    platform_name: str | None = None,
    knowledge_docs: list[Path] | None = None,
    bm25_index: Path | None = None,
    faiss_index: Path | None = None,
    *,
    force_rebuild: bool = False,
) -> HybridRetriever | None:
    """建立或載入 HybridRetriever."""
    from logsensing.rag import (
        BM25Index,
        HybridRetriever,
        get_platform_rag_store,
        list_experience_docs,
    )

    store = None
    experience_docs: list[Path] = []
    if platform_name:
        store = get_platform_rag_store(Path(cfg.rag.index_root), platform_name)
        experience_docs = list_experience_docs(
            store,
            prefer_compact=cfg.rag.prefer_compact_experience,
        )

    doc_paths = _resolve_knowledge_docs(cfg, knowledge_docs, platform_name=platform_name)
    source_paths: list[Path] = []
    seen_paths: set[str] = set()
    for path in [*doc_paths, *experience_docs]:
        resolved_key = str(path.resolve())
        if resolved_key not in seen_paths:
            source_paths.append(path)
            seen_paths.add(resolved_key)

    bm25_path = _resolve_rag_index_path(bm25_index, cfg.rag.bm25_index_path)
    if bm25_path is None and store is not None:
        bm25_path = store.bm25_index_path
    faiss_path = _resolve_rag_index_path(faiss_index, cfg.rag.faiss_index_path)
    if faiss_path is None and store is not None:
        faiss_path = store.faiss_index_path

    has_existing_index = (
        (bm25_path is not None and bm25_path.exists())
        or (faiss_path is not None and faiss_path.exists())
    )
    if not source_paths and not has_existing_index:
        return None

    bm25 = None
    vector = None
    backend_name = cfg.rag.vector_backend.lower().strip()

    if not force_rebuild and bm25_path is not None and bm25_path.exists():
        try:
            bm25 = BM25Index()
            bm25.load(bm25_path)
            console.print(f"[dim]已載入 BM25 索引: {bm25_path}[/dim]")
        except ImportError as exc:
            console.print("[red]RAG 相依未安裝，請執行: uv sync --extra rag[/red]")
            raise typer.Exit(code=1) from exc

    if not force_rebuild and faiss_path is not None and faiss_path.exists():
        vector, vector_backend = _load_vector_backend(
            cfg,
            faiss_path,
            backend_name=backend_name,
        )
        if vector is not None:
            console.print(f"[dim]已載入向量索引 ({vector_backend}): {faiss_path}[/dim]")

    if source_paths and (force_rebuild or bm25 is None or vector is None):
        chunks = _chunk_knowledge_docs(
            cfg,
            source_paths,
            platform_name=platform_name,
            experience_paths=experience_docs,
        )
        if not chunks:
            console.print("[yellow]知識庫文件未產生任何 chunks，略過 RAG[/yellow]")
        else:
            console.print(
                f"[dim]RAG 讀入 {len(source_paths)} 個來源，切成 {len(chunks)} 個 chunks[/dim]"
            )
            if force_rebuild or bm25 is None:
                try:
                    bm25 = BM25Index()
                    bm25.build(chunks)
                except ImportError as exc:
                    console.print("[red]RAG 相依未安裝，請執行: uv sync --extra rag[/red]")
                    raise typer.Exit(code=1) from exc
                if bm25_path is not None:
                    bm25_path.parent.mkdir(parents=True, exist_ok=True)
                    bm25.save(bm25_path)
                    console.print(f"[dim]已儲存 BM25 索引: {bm25_path}[/dim]")

            if force_rebuild or vector is None:
                vector, vector_backend = _build_vector_backend(
                    cfg,
                    chunks,
                    backend_name=backend_name,
                )
                if vector is not None and faiss_path is not None:
                    vector.save(faiss_path)
                    console.print(
                        f"[dim]已儲存向量索引 ({vector_backend}): {faiss_path}[/dim]"
                    )

    if bm25 is None and vector is None:
        return None

    backends = []
    if bm25 is not None:
        backends.append("BM25")
    if vector is not None:
        backends.append("Vector")
    console.print(f"[green]✓ RAG 知識庫已啟用 ({' + '.join(backends)})[/green]")
    return HybridRetriever(bm25=bm25, vector=vector)


def _load_vector_backend(
    cfg: AppConfig,
    path: Path,
    *,
    backend_name: str,
) -> tuple[VectorSearchBackend | None, str]:
    if backend_name == "turboquant":
        from logsensing.rag.turboquant import TurboQuantVectorIndex

        candidate = TurboQuantVectorIndex(
            bit_width=cfg.rag.vector_compression_bits,
            rotation_seed=cfg.rag.vector_rotation_seed,
        )
        if candidate.is_available:
            try:
                candidate.load(path)
                return candidate, "turboquant"
            except (FileNotFoundError, ValueError):
                console.print(
                    "[yellow]TurboQuant 索引載入失敗，將在需要時重建或回退其他後端。[/yellow]"
                )
        else:
            console.print(
                "[yellow]TurboQuant 向量相依未安裝，嘗試回退 FAISS 載入。[/yellow]"
            )

    from logsensing.rag.vector import VectorIndex

    fallback = VectorIndex()
    if fallback.is_available:
        try:
            fallback.load(path)
            return fallback, "faiss"
        except (FileNotFoundError, ValueError, KeyError):
            console.print(
                "[yellow]FAISS 索引載入失敗，將在需要時重建索引。[/yellow]"
            )
    console.print(
        "[yellow]向量檢索相依未安裝，略過 FAISS 載入。"
        "安裝方式: uv sync --extra rag[/yellow]"
    )
    return None, backend_name


def _build_vector_backend(
    cfg: AppConfig,
    chunks: list[Chunk],
    *,
    backend_name: str,
) -> tuple[VectorSearchBackend | None, str]:
    if backend_name == "turboquant":
        from logsensing.rag.turboquant import TurboQuantVectorIndex

        compressed = TurboQuantVectorIndex(
            bit_width=cfg.rag.vector_compression_bits,
            rotation_seed=cfg.rag.vector_rotation_seed,
        )
        if compressed.is_available:
            compressed.build(chunks)
            return compressed, "turboquant"
        console.print(
            "[yellow]TurboQuant 向量相依未安裝，嘗試回退 FAISS backend。[/yellow]"
        )

    from logsensing.rag.vector import VectorIndex

    fallback = VectorIndex()
    if fallback.is_available:
        fallback.build(chunks)
        return fallback, "faiss"

    console.print(
        "[yellow]向量檢索相依未安裝，RAG 降級為 BM25-only。"
        "安裝方式: uv sync --extra rag[/yellow]"
    )
    return None, backend_name


def _load_cycle_log_lines(
    cfg: AppConfig,
    logfile: Path | None,
    platform_name: str | None = None,
) -> dict[int, list[str]]:
    """讀取並切割 cycle log lines."""
    if logfile is None or not logfile.exists():
        return {}

    plat = _resolve_platform(platform_name, logfile, cfg)
    splitter = _build_splitter(cfg, platform=plat)
    with open(logfile, encoding=cfg.parser.encoding, errors="replace") as fh:
        cycles = list(splitter.split(fh))

    log_lines: dict[int, list[str]] = {}
    for cycle in cycles:
        log_lines[cycle.cycle_id] = list(splitter.read_cycle_lines(logfile, cycle))
    return log_lines


def _write_platform_experience(
    cfg: AppConfig,
    *,
    platform_name: str | None,
    logfile: Path | None,
    anomalies_data: dict[str, Any],
    drain_data: dict[str, Any],
    analysis_text: str,
    generated_by: str,
    model_name: str | None = None,
    knowledge_docs: list[Path] | None = None,
    bm25_index: Path | None = None,
    faiss_index: Path | None = None,
) -> None:
    """Persist one analysis result into the platform's RAG memory store."""
    if not cfg.rag.auto_writeback:
        return
    if platform_name is None:
        console.print("[dim]無法判定平台，略過經驗回寫[/dim]")
        return
    if logfile is None or not logfile.exists():
        console.print("[dim]未提供原始 log，略過經驗回寫[/dim]")
        return

    from logsensing.rag import (
        build_experience_artifact,
        get_platform_rag_store,
        write_experience_artifact,
    )

    store = get_platform_rag_store(Path(cfg.rag.index_root), platform_name)
    device_model = anomalies_data.get("resource", {}).get("device.model", "unknown")
    compressor = None
    if cfg.parser.aaak_enabled:
        from logsensing.parser.aaak import AAAKLogCompressor

        compressor = AAAKLogCompressor(
            cfg.parser.aaak_entity_map,
            max_summary_items=cfg.parser.aaak_max_summary_items,
        )
    artifact = build_experience_artifact(
        platform=platform_name,
        device_model=device_model,
        logfile=logfile,
        anomalies_data=anomalies_data,
        drain_state=drain_data,
        analysis_text=analysis_text,
        generated_by=generated_by,
        model_name=model_name,
        compressor=compressor,
    )
    md_path, created = write_experience_artifact(store, artifact)
    if created:
        console.print(f"[dim]已寫入平台經驗: {md_path}[/dim]")
        _build_rag_retriever(
            cfg,
            platform_name=platform_name,
            knowledge_docs=knowledge_docs,
            bm25_index=bm25_index,
            faiss_index=faiss_index,
            force_rebuild=True,
        )
    else:
        console.print(f"[dim]平台經驗已存在，略過回寫: {md_path.name}[/dim]")


# ---------------------------------------------------------------------------
# Type aliases for Typer Annotated
# ---------------------------------------------------------------------------

LogfileArg = Annotated[Path, typer.Argument(help="日誌檔案路徑", exists=True)]
ConfigOpt = Annotated[Path | None, typer.Option("--config", "-c", help="TOML 組態檔路徑")]
PlatformOpt = Annotated[
    str | None,
    typer.Option("--platform", "-p", help="平台 (auto/bdk/prplos)"),
]
KnowledgeDocsOpt = Annotated[
    list[Path] | None,
    typer.Option("--knowledge-doc", help="知識庫文件路徑，可重複指定"),
]
Bm25IndexOpt = Annotated[
    Path | None,
    typer.Option("--bm25-index", help="BM25 索引 JSON 路徑"),
]
FaissIndexOpt = Annotated[
    Path | None,
    typer.Option("--faiss-index", help="FAISS 索引目錄路徑"),
]


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


@app.command()
def parse(
    logfile: LogfileArg,
    output: Annotated[Path, typer.Option("--output", "-o", help="輸出目錄")] = Path("output"),
    anchors: Annotated[list[str] | None, typer.Option("--anchors", help="錨點字串")] = None,
    config: ConfigOpt = None,
    platform: PlatformOpt = None,
) -> None:
    """解析日誌，切割 Boot Cycles 並探勘模板."""
    from logsensing.parser.demux import Demultiplexer

    cfg = _load_config(config)
    plat = _resolve_platform(platform, logfile, cfg)
    splitter = _build_splitter(cfg, anchors, platform=plat)
    drain = _build_drain(cfg)
    demux = Demultiplexer.from_platform(plat)

    output.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        prog.add_task("切割 Boot Cycles …", total=None)
        with open(logfile, encoding=cfg.parser.encoding, errors="replace") as fh:
            cycles = list(splitter.split(fh))

    table = Table(title="Boot Cycles 摘要")
    table.add_column("Cycle", justify="right")
    table.add_column("Lines", justify="right")
    table.add_column("Templates", justify="right")
    table.add_column("Channels", justify="right")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        task = prog.add_task("解析中 …", total=len(cycles))
        for cycle in cycles:
            lines = list(splitter.read_cycle_lines(logfile, cycle))
            parsed = list(drain.parse_lines(iter(lines)))
            channels = demux.demux(iter(parsed))
            templates = drain.get_templates()
            non_empty_ch = sum(1 for ch in channels.values() if ch.line_count > 0)
            table.add_row(
                str(cycle.cycle_id),
                str(cycle.line_count),
                str(len(templates)),
                str(non_empty_ch),
            )
            prog.advance(task)

    console.print(table)

    state_path = output / "drain_state.json"
    drain.save_state(state_path)
    console.print(f"[green]✓ Drain3 狀態已儲存至 {state_path}[/green]")
    n_tpl = len(drain.get_templates())
    if cfg.parser.aaak_enabled:
        from logsensing.parser.aaak import AAAKLogCompressor

        compressor = AAAKLogCompressor(
            cfg.parser.aaak_entity_map,
            max_summary_items=cfg.parser.aaak_max_summary_items,
        )
        compact_templates = compressor.compress_templates(drain.get_templates())
        if compact_templates:
            compact_path = output / "templates.aaak"
            compact_path.write_text(f"{compact_templates}\n", encoding="utf-8")
            console.print(f"[green]✓ AAAK 模板摘要已儲存至 {compact_path}[/green]")
    console.print(f"[green]✓ 共 {len(cycles)} 個 cycles，{n_tpl} 個模板[/green]")


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


@app.command()
def analyze(
    logfile: LogfileArg,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="輸出 JSON 路徑")] = None,
    config: ConfigOpt = None,
    baseline: Annotated[
        Path | None, typer.Option("--baseline", "-b", help="Baseline JSON 路徑")
    ] = None,
    device_model: Annotated[str, typer.Option("--device-model", help="裝置型號")] = "unknown",
    platform: PlatformOpt = None,
) -> None:
    """分析異常，產出 OTel JSON."""
    from logsensing.analyzer.baseline import BaselineProfiler
    from logsensing.analyzer.detector import AnomalyDetector
    from logsensing.analyzer.exporter import OTelExporter

    cfg = _load_config(config)
    plat = _resolve_platform(platform, logfile, cfg)
    splitter = _build_splitter(cfg, platform=plat)
    profiler = BaselineProfiler.from_platform(plat)
    baseline_profile = None

    if baseline is not None and baseline.exists():
        baseline_profile = profiler.load(baseline)

    detector = AnomalyDetector.from_platform(
        plat,
        baseline=baseline_profile,
        context_lines_before=cfg.analyzer.context_lines_before,
        context_lines_after=cfg.analyzer.context_lines_after,
    )

    if output is None:
        output = Path("anomalies.json")

    all_anomalies: list[Any] = []

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        prog.add_task("切割 Boot Cycles …", total=None)
        with open(logfile, encoding=cfg.parser.encoding, errors="replace") as fh:
            cycles = list(splitter.split(fh))

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        task = prog.add_task("分析中 …", total=len(cycles))
        for cycle in cycles:
            lines = list(splitter.read_cycle_lines(logfile, cycle))
            profile = profiler.profile_cycle(lines, cycle_id=cycle.cycle_id)
            anomalies = detector.detect(lines, cycle.cycle_id, cycle_profile=profile)
            all_anomalies.extend(anomalies)
            prog.advance(task)

    exporter = OTelExporter(device_model=device_model)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = exporter.export(all_anomalies, output_path=output)

    # Summary table
    table = Table(title="異常偵測摘要")
    table.add_column("嚴重度", justify="center")
    table.add_column("數量", justify="right")
    summary = result.get("summary", {})
    by_sev = summary.get("by_severity", {})
    for sev in ("critical", "warning", "info"):
        count = by_sev.get(sev, 0)
        if count > 0:
            table.add_row(sev, str(count))
    if not by_sev:
        table.add_row("—", "0")
    console.print(table)

    n_anom = len(all_anomalies)
    n_cyc = len(summary.get("affected_cycles", []))
    console.print(f"[green]✓ 共偵測到 {n_anom} 個異常，影響 {n_cyc} 個 cycles[/green]")
    console.print(f"[green]✓ 結果已匯出至 {output}[/green]")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@app.command()
def report(
    logfile: LogfileArg,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Markdown 報告輸出路徑")
    ] = None,
    device_model: Annotated[
        str, typer.Option("--device-model", help="裝置型號")
    ] = "unknown",
    skip_cycles: Annotated[
        int, typer.Option("--skip-cycles", help="跳過前 N 個 cycles")
    ] = 2,
    config: ConfigOpt = None,
    platform: PlatformOpt = None,
) -> None:
    """產生開機時間統計報告."""
    from logsensing.analyzer.reporter import BootTimingAnalyzer

    cfg = _load_config(config)
    plat = _resolve_platform(platform, logfile, cfg)
    analyzer = BootTimingAnalyzer.from_platform(plat, skip_first_n=skip_cycles)

    console.print(f"[dim]平台: {plat.display_name}[/dim]")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        prog.add_task("分析開機時間 …", total=None)
        result = analyzer.analyze(logfile, device_model=device_model)

    if result.supports_timing:
        # Boot time summary table
        summary_table = Table(title="開機時間摘要")
        summary_table.add_column("指標")
        summary_table.add_column("值", justify="right")
        summary_table.add_row("平均", f"{result.boot_time_mean:.3f}s")
        summary_table.add_row("標準差", f"{result.boot_time_stddev:.3f}s")
        summary_table.add_row("最小", f"{result.boot_time_min:.3f}s")
        summary_table.add_row("最大", f"{result.boot_time_max:.3f}s")
        summary_table.add_row("有效 Cycles", str(result.valid_cycles))
        console.print(summary_table)
        console.print()
    else:
        console.print(f"[yellow]⚠ 平台 {plat.name} 無 timestamp，改用序列分析（行號）[/yellow]")
        console.print(f"有效 Cycles: {result.valid_cycles}")
        console.print()

    # Process wake time table
    unit = "s" if result.supports_timing else "行"
    proc_table = Table(title=f"Process/Module Wake Time (相對 cycle 起始, 單位: {unit})")
    proc_table.add_column("Process")
    proc_table.add_column("Mean", justify="right")
    proc_table.add_column("StdDev", justify="right")
    proc_table.add_column("Min", justify="right")
    proc_table.add_column("Max", justify="right")
    proc_table.add_column("Hit%", justify="right")
    fmt = ".3f" if result.supports_timing else ".0f"
    for ps in result.process_stats:
        if ps.hit_count == 0:
            proc_table.add_row(ps.name, "N/A", "N/A", "N/A", "N/A", "0%")
        else:
            pct = (
                ps.hit_count / ps.total_cycles * 100
                if ps.total_cycles > 0
                else 0
            )
            proc_table.add_row(
                ps.name,
                f"{ps.mean:{fmt}}{unit}",
                f"{ps.stddev:{fmt}}{unit}",
                f"{ps.min_val:{fmt}}{unit}",
                f"{ps.max_val:{fmt}}{unit}",
                f"{pct:.0f}%",
            )
    console.print(proc_table)
    console.print()

    # Per-cycle timing table (compact: show first 5 key milestones from platform)
    cycle_table = Table(title="Per-Cycle Boot Time")
    cycle_table.add_column("Cycle", justify="right")
    cycle_table.add_column("Total", justify="right")
    key_procs = [p[0] for p in plat.processes[:5]] if plat.processes else []
    for kp in key_procs:
        cycle_table.add_column(kp, justify="right")

    for ct in result.cycle_timings:
        offsets = ct.process_offsets if result.supports_timing else {
            k: float(v) for k, v in ct.process_line_offsets.items()
        }
        total = ct.total_seconds if result.supports_timing else ct.total_lines
        row = [str(ct.cycle_id), f"{total:{fmt}}{unit}"]
        for kp in key_procs:
            if kp in offsets:
                row.append(f"{offsets[kp]:{fmt}}{unit}")
            else:
                row.append("N/A")
        cycle_table.add_row(*row)
    console.print(cycle_table)

    # Save to markdown
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        md = analyzer.to_markdown(result)
        output.write_text(md, encoding="utf-8")
        console.print(f"\n[green]✓ 報告已儲存至 {output}[/green]")

    console.print(
        f"\n[green]✓ 裝置: {device_model}，"
        f"{result.total_cycles} cycles 分析完成[/green]"
    )


# ---------------------------------------------------------------------------
# train baseline
# ---------------------------------------------------------------------------


@train_app.command("baseline")
def train_baseline(
    logfile: Annotated[Path, typer.Argument(help="正常日誌檔案路徑", exists=True)],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Baseline JSON 輸出路徑")
    ] = None,
    config: ConfigOpt = None,
    platform: PlatformOpt = None,
) -> None:
    """從正常日誌訓練 baseline profile."""
    from logsensing.analyzer.baseline import BaselineProfiler

    cfg = _load_config(config)
    plat = _resolve_platform(platform, logfile, cfg)
    splitter = _build_splitter(cfg, platform=plat)
    profiler = BaselineProfiler.from_platform(plat)

    if output is None:
        output = Path("baseline.json")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        prog.add_task("切割 Boot Cycles …", total=None)
        with open(logfile, encoding=cfg.parser.encoding, errors="replace") as fh:
            cycles = list(splitter.split(fh))

    profiles = []
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        task = prog.add_task("Profiling cycles …", total=len(cycles))
        for cycle in cycles:
            lines = list(splitter.read_cycle_lines(logfile, cycle))
            profile = profiler.profile_cycle(lines, cycle_id=cycle.cycle_id)
            profiles.append(profile)
            prog.advance(task)

    baseline_profile = profiler.train(profiles)
    profiler.save(output)

    table = Table(title="Baseline Milestone Deltas")
    table.add_column("Milestone Pair")
    table.add_column("Mean (s)", justify="right")
    table.add_column("StdDev (s)", justify="right")
    for key in sorted(baseline_profile.mean_deltas):
        table.add_row(
            key,
            f"{baseline_profile.mean_deltas[key]:.3f}",
            f"{baseline_profile.stddev_deltas.get(key, 0.0):.3f}",
        )
    console.print(table)

    console.print(
        f"[green]✓ Baseline 已儲存至 {output} "
        f"(從 {baseline_profile.sample_count} 個 cycles 訓練)[/green]"
    )


# ---------------------------------------------------------------------------
# train drain
# ---------------------------------------------------------------------------


@train_app.command("drain")
def train_drain(
    logfile: LogfileArg,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Drain3 狀態輸出路徑")
    ] = None,
    config: ConfigOpt = None,
) -> None:
    """從日誌訓練 Drain3 模板模型."""
    cfg = _load_config(config)
    splitter = _build_splitter(cfg)
    drain = _build_drain(cfg)

    if output is None:
        output = Path("drain_state.json")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        prog.add_task("切割 Boot Cycles …", total=None)
        with open(logfile, encoding=cfg.parser.encoding, errors="replace") as fh:
            cycles = list(splitter.split(fh))

    total_lines = 0
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}")
    ) as prog:
        task = prog.add_task("訓練 Drain3 …", total=len(cycles))
        for cycle in cycles:
            lines = list(splitter.read_cycle_lines(logfile, cycle))
            list(drain.parse_lines(iter(lines)))
            total_lines += len(lines)
            prog.advance(task)

    output.parent.mkdir(parents=True, exist_ok=True)
    drain.save_state(output)

    templates = drain.get_templates()

    table = Table(title="Drain3 模板摘要")
    table.add_column("ID", justify="right")
    table.add_column("Count", justify="right")
    table.add_column("Template", max_width=80)
    for t in sorted(templates, key=lambda x: x.count, reverse=True)[:20]:
        table.add_row(str(t.template_id), str(t.count), t.template)
    if len(templates) > 20:
        table.add_row("…", "…", f"(共 {len(templates)} 個模板)")
    console.print(table)

    console.print(
        f"[green]✓ Drain3 狀態已儲存至 {output} "
        f"({len(templates)} 個模板，{total_lines} 行已處理)[/green]"
    )


# ---------------------------------------------------------------------------
# agent (placeholders)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "你是 LogSensing 的日誌分析 AI 助手。你可以使用工具查詢異常事件、日誌、"
    "Drain3 模板、基準線與文件知識庫。請根據查詢結果提供根因分析與建議。"
    "回覆使用繁體中文。"
)


@agent_app.command("analyze")
def agent_analyze(
    anomalies: Annotated[
        Path | None, typer.Option("--anomalies", help="異常 JSON 路徑")
    ] = None,
    baseline: Annotated[
        Path | None, typer.Option("--baseline", "-b", help="Baseline JSON 路徑")
    ] = None,
    drain_state: Annotated[
        Path | None, typer.Option("--drain-state", help="Drain3 狀態 JSON 路徑")
    ] = None,
    logfile: Annotated[
        Path | None, typer.Option("--logfile", "-l", help="原始日誌檔案路徑")
    ] = None,
    cycle: Annotated[int | None, typer.Option("--cycle", help="指定 cycle 編號")] = None,
    model: Annotated[str, typer.Option("--model", help="LLM 模型名稱")] = "gpt-4o",
    api_base: Annotated[str | None, typer.Option("--api-base", help="API 端點")] = None,
    config: ConfigOpt = None,
    platform: PlatformOpt = None,
    knowledge_docs: KnowledgeDocsOpt = None,
    bm25_index: Bm25IndexOpt = None,
    faiss_index: FaissIndexOpt = None,
) -> None:
    """使用 AI Agent 分析異常，產出 RCA 報告."""
    import json as _json

    cfg = _load_config(config)
    rag_platform = _resolve_rag_platform(cfg, platform, logfile)
    rag_platform_name = rag_platform.name if rag_platform is not None else None

    # Load data files
    anomalies_data: dict[str, Any] = {}
    baseline_data: dict[str, Any] = {}
    drain_data: dict[str, Any] = {}
    if anomalies and anomalies.exists():
        anomalies_data = _json.loads(anomalies.read_text(encoding="utf-8"))
    else:
        default_anom = Path("anomalies.json")
        if default_anom.exists():
            anomalies_data = _json.loads(default_anom.read_text(encoding="utf-8"))

    if baseline and baseline.exists():
        baseline_data = _json.loads(baseline.read_text(encoding="utf-8"))

    if drain_state and drain_state.exists():
        drain_data = _json.loads(drain_state.read_text(encoding="utf-8"))

    log_lines = _load_cycle_log_lines(cfg, logfile, rag_platform_name or platform)

    if not anomalies_data.get("traces"):
        console.print("[yellow]未找到異常資料，請先執行 logsensing analyze[/yellow]")
        raise typer.Exit(code=1)

    # Try LLM-based analysis
    try:
        from logsensing.agent.llm import LLMClient
        from logsensing.agent.tools import AgentToolkit

        llm_model = model or cfg.agent.model
        llm_api_base = api_base or cfg.agent.api_base or None
        client = LLMClient(
            model=llm_model,
            api_base=llm_api_base,
            temperature=cfg.agent.temperature,
            max_tokens=cfg.agent.max_tokens,
        )
        retriever = _build_rag_retriever(
            cfg,
            platform_name=rag_platform_name,
            knowledge_docs=knowledge_docs,
            bm25_index=bm25_index,
            faiss_index=faiss_index,
        )
        toolkit = AgentToolkit(
            anomalies_data=anomalies_data,
            baseline_data=baseline_data,
            drain_state=drain_data,
            log_lines=log_lines,
            retriever=retriever,
        )
        toolkit.register_all(client)

        cycle_hint = f" (Cycle #{cycle})" if cycle else ""
        user_msg = (
            f"請分析以下系統的異常事件{cycle_hint}，產出完整的根因分析 (RCA) 報告。"
            "請使用工具取得異常清單、相關日誌與基準線；若需要平台/規格背景，也請搜尋知識庫。"
        )

        with console.status("[bold green]AI Agent 分析中 …"):
            result = client.chat(
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=_SYSTEM_PROMPT,
            )

        from rich.markdown import Markdown

        console.print(Markdown(result))
        _write_platform_experience(
            cfg,
            platform_name=rag_platform_name,
            logfile=logfile,
            anomalies_data=anomalies_data,
            drain_data=drain_data,
            analysis_text=result,
            generated_by="llm",
            model_name=client.model,
            knowledge_docs=knowledge_docs,
            bm25_index=bm25_index,
            faiss_index=faiss_index,
        )

    except ImportError:
        # Fall back to rule-based RCA
        console.print(
            "[yellow]openai 未安裝，使用規則式 RCA 報告。"
            "安裝 LLM 支援: uv sync --extra agent[/yellow]\n"
        )
        from logsensing.agent.rca import RCAReport

        rca = RCAReport(anomalies_data=anomalies_data)
        if cycle is not None:
            md = rca.generate_cycle_report(cycle)
        else:
            md = rca.generate_summary_report()

        from rich.markdown import Markdown

        console.print(Markdown(md))
        _write_platform_experience(
            cfg,
            platform_name=rag_platform_name,
            logfile=logfile,
            anomalies_data=anomalies_data,
            drain_data=drain_data,
            analysis_text=md,
            generated_by="rule-based",
            knowledge_docs=knowledge_docs,
            bm25_index=bm25_index,
            faiss_index=faiss_index,
        )


@agent_app.command("chat")
def agent_chat(
    anomalies: Annotated[
        Path | None, typer.Option("--anomalies", help="異常 JSON 路徑")
    ] = None,
    baseline: Annotated[
        Path | None, typer.Option("--baseline", "-b", help="Baseline JSON 路徑")
    ] = None,
    drain_state: Annotated[
        Path | None, typer.Option("--drain-state", help="Drain3 狀態 JSON 路徑")
    ] = None,
    logfile: Annotated[
        Path | None, typer.Option("--logfile", "-l", help="原始日誌檔案路徑")
    ] = None,
    model: Annotated[str, typer.Option("--model", help="LLM 模型名稱")] = "gpt-4o",
    api_base: Annotated[str | None, typer.Option("--api-base", help="API 端點")] = None,
    config: ConfigOpt = None,
    platform: PlatformOpt = None,
    knowledge_docs: KnowledgeDocsOpt = None,
    bm25_index: Bm25IndexOpt = None,
    faiss_index: FaissIndexOpt = None,
) -> None:
    """與 AI Agent 對話，互動式分析日誌."""
    import json as _json

    cfg = _load_config(config)
    rag_platform = _resolve_rag_platform(cfg, platform, logfile)
    rag_platform_name = rag_platform.name if rag_platform is not None else None

    anomalies_data: dict[str, Any] = {}
    baseline_data: dict[str, Any] = {}
    drain_data: dict[str, Any] = {}
    if anomalies and anomalies.exists():
        anomalies_data = _json.loads(anomalies.read_text(encoding="utf-8"))
    if baseline and baseline.exists():
        baseline_data = _json.loads(baseline.read_text(encoding="utf-8"))
    if drain_state and drain_state.exists():
        drain_data = _json.loads(drain_state.read_text(encoding="utf-8"))
    log_lines = _load_cycle_log_lines(cfg, logfile, rag_platform_name or platform)

    # Try LLM chat
    try:
        from logsensing.agent.llm import LLMClient
        from logsensing.agent.tools import AgentToolkit

        llm_model = model or cfg.agent.model
        llm_api_base = api_base or cfg.agent.api_base or None
        client = LLMClient(
            model=llm_model,
            api_base=llm_api_base,
            temperature=cfg.agent.temperature,
            max_tokens=cfg.agent.max_tokens,
        )
        retriever = _build_rag_retriever(
            cfg,
            platform_name=rag_platform_name,
            knowledge_docs=knowledge_docs,
            bm25_index=bm25_index,
            faiss_index=faiss_index,
        )
        toolkit = AgentToolkit(
            anomalies_data=anomalies_data,
            baseline_data=baseline_data,
            drain_state=drain_data,
            log_lines=log_lines,
            retriever=retriever,
        )
        toolkit.register_all(client)

        from rich.markdown import Markdown
        from rich.prompt import Prompt

        console.print("[bold green]LogSensing AI Chat[/bold green]")
        rag_status = "on" if retriever is not None else "off"
        console.print(f"[dim]模型: {client.model} | RAG: {rag_status} | 輸入 'quit' 離開[/dim]\n")

        history: list[dict[str, str]] = []
        while True:
            try:
                user_input = Prompt.ask("[bold blue]you[/bold blue]")
            except (KeyboardInterrupt, EOFError):
                break
            if user_input.strip().lower() in ("quit", "exit"):
                break
            if not user_input.strip():
                continue

            history.append({"role": "user", "content": user_input})
            with console.status("[bold green]思考中 …"):
                reply = client.chat(messages=history, system_prompt=_SYSTEM_PROMPT)
            history.append({"role": "assistant", "content": reply})
            console.print()
            console.print(Markdown(reply))
            console.print()

        console.print("\n[dim]Bye![/dim]")

    except ImportError:
        # Fall back to rule-based interactive agent
        console.print(
            "[yellow]openai 未安裝，使用規則式互動 Agent。"
            "安裝 LLM 支援: uv sync --extra agent[/yellow]\n"
        )
        from logsensing.agent.interactive import InteractiveAgent

        agent = InteractiveAgent(
            anomalies_path=anomalies,
            baseline_path=baseline,
            drain_state_path=drain_state,
            log_path=logfile,
        )
        agent.run()


if __name__ == "__main__":
    app()
