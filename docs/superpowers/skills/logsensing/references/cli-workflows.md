# Logsensing CLI Workflows

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

If `uv sync` fails, stop and report the root cause instead of trying `pip install`.
