# Logsensing CLI Workflows

## Dependency guidance

- Base CLI readiness and repair uses `uv sync`.
- LLM-backed `agent analyze` and `agent chat` require `uv sync --extra agent`.
- RAG indexing and `--knowledge-doc` workflows require `uv sync --extra rag`.
- Combined agent + knowledge-doc workflows may require both extras: `uv sync --extra agent --extra rag`.
- If only the base install is present, do not describe `agent` output as LLM-backed; the CLI may fall back to rule-based behavior instead.

## Analyze one log

```bash
uv run logsensing analyze /path/to/device.log --output output/device.anomalies.json
uv run logsensing report /path/to/device.log --output output/device.report.md
```

Return the output paths, top anomaly rules, affected cycles, issue line numbers, and timestamps when useful.

## Analyze multiple logs

Run one `analyze`/`report` pair per log and summarize cross-log common rules before showing raw evidence.

## Train baseline or Drain state

```bash
uv run logsensing train baseline /path/to/normal.log --output output/baseline.json
uv run logsensing train drain /path/to/device.log --output output/drain_state.json
```

## Agent and RAG workflows

Before running these commands, install the matching optional dependencies:

```bash
uv sync --extra agent
uv sync --extra rag
```

Use both extras together when the workflow combines agent commands with knowledge-doc indexing.

```bash
uv run logsensing agent analyze --anomalies output/device.anomalies.json --logfile /path/to/device.log
uv run logsensing agent chat --logfile /path/to/device.log --knowledge-doc docs/spec.md
```

## Environment repair

```bash
uv run logsensing --help
uv sync
uv run logsensing --help
```

If the CLI reports missing agent support, run `uv sync --extra agent`.

If the CLI reports missing RAG support, run `uv sync --extra rag`.

If `uv sync` or either extra sync fails, stop and report the root cause instead of trying `pip install`.
