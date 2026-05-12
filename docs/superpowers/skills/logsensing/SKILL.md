---
name: logsensing
description: Use logsensing CLI workflows from natural-language requests covering analysis, triage, training, RAG, and safe environment repair.
---

# logsensing

Use this skill when the user wants to scan logs, summarize anomalies, train baselines, rebuild Drain state, or use logsensing RAG and agent workflows.

## Core rules

- Work inside the `logsensing` repository.
- Prefer `uv run logsensing ...` over direct system Python execution.
- Before running a workflow, check `uv` and `uv run logsensing --help`.
- If readiness fails, only attempt the documented repair path: `uv sync`.
- If repair still fails, stop and report the root cause plainly.
- Keep outputs compact: one-line conclusion, artifact paths, top findings, affected cycles, line numbers, and timestamps when useful.
- Do not dump large raw logs unless the user explicitly asks.
- If required inputs are missing, ask only for the minimum missing detail.

## Input normalization

Accept and normalize:

1. local log file paths
2. pasted log snippets
3. `config.toml` paths
4. `baseline.json` or `anomalies.json` paths
5. knowledge document paths
6. mixed requests that combine the above

If a required path does not exist, say which path is missing and stop.

## Routing

### analyze

Use for log scanning and timing summaries.

Commands:

- `uv run logsensing analyze <log> --output <anomalies>`
- `uv run logsensing report <log> --output <report>`

Return:

- one-line conclusion
- artifact paths
- top anomaly rules
- affected cycles
- line numbers
- timestamps when available

### triage

Use for existing anomalies, reports, or pasted snippets.

Behavior:

- group dominant issue clusters
- point to line numbers and timestamps
- prefer `anomalies.json` or report outputs over reopening full raw logs
- provide compact RCA hints and next inspection targets

### baseline_train

Use for `train baseline` and `train drain`.

Commands:

- `uv run logsensing train baseline <log> --output <baseline>`
- `uv run logsensing train drain <log> --output <drain_state>`

Return the artifact path and what it is for.

### rag_agent

Use for `agent analyze`, `agent chat`, knowledge docs, and platform RAG follow-up work.

Commands:

- `uv run logsensing agent analyze ...`
- `uv run logsensing agent chat ...`

Return the analysis summary, knowledge inputs used, and any index/store paths needed for follow-up work.

### env_repair

Use before other workflows when runtime readiness is uncertain or when the user explicitly asks to fix the environment.

Readiness sequence:

1. check `uv`
2. run `uv run logsensing --help`
3. if needed, run `uv sync`
4. re-run `uv run logsensing --help`

If any step fails, stop with the failing command and root cause.

## Context budget

- prefer summaries, counts, top-N findings, and representative excerpts
- prefer structured outputs over full raw logs
- compress large snippets into issue clusters and line-numbered highlights before deeper reasoning

## Reference

Read `references/cli-workflows.md` for concrete command examples.
