# Logsensing Skill Design

## Problem

`logsensing` already has a capable CLI, but using it through Copilot still requires the model to remember repo setup, choose the right command, keep context usage under control, and stop safely when the environment is broken. We need a single skill that turns natural requests into the right `logsensing` workflow without forcing the user to remember subcommands or recover the environment manually.

## Goals

1. Provide a single `logsensing` skill as the entrypoint for analysis, triage, training, RAG, and agent workflows.
2. Prefer the repository's `uv`-managed runtime and existing CLI flows.
3. Keep context usage small so analysis space is preserved for actual log reasoning.
4. Support mixed inputs: file paths, pasted snippets, config files, baselines, anomalies, and knowledge docs.
5. Auto-repair only low-risk environment issues; otherwise stop and report root cause clearly.
6. Keep a version-controlled source in the repo and a usable installed copy in the user skill directory.

## Non-Goals

1. Replacing the `logsensing` CLI.
2. Inventing new install flows outside the repo's documented `uv` workflow.
3. Dumping large raw logs directly into the chat when structured outputs can be used instead.
4. Splitting the experience across multiple user-facing skills.

## Recommended Shape

Use one top-level skill named `logsensing`.

Internally, the skill routes requests into a small set of playbooks instead of exposing multiple skill names:

- `analyze`
- `triage`
- `baseline_train`
- `rag_agent`
- `env_repair`

This keeps the user-facing surface simple while still giving the skill predictable internal branches.

## Supported Inputs

The skill should accept and normalize:

1. One or more local log file paths.
2. Pasted log snippets.
3. `config.toml` or other config paths.
4. `baseline.json`, `anomalies.json`, and other structured outputs.
5. Knowledge document paths for RAG workflows.
6. Mixed requests that combine several of the above in one prompt.

If a required path does not exist, the skill should stop and say exactly which path is missing.

## Routing Model

### 1. Analyze

Use when the request is about scanning logs, generating anomalies, or producing timing summaries.

Primary commands:

- `uv run logsensing analyze ...`
- `uv run logsensing report ...`

Expected outputs:

- anomalies JSON path
- report path when requested
- compact summary of top rules, affected cycles, line numbers, and representative evidence

### 2. Triage

Use when the request is about understanding existing anomalies, pasted snippets, or narrowing down likely causes.

Inputs may include:

- raw log snippets
- `anomalies.json`
- report outputs
- one or more original log files for follow-up lookup

Behavior:

- summarize dominant anomaly clusters
- point to issue line numbers and timestamps when available
- provide compact RCA hints and next inspection targets

### 3. Baseline/Train

Use when the request explicitly mentions baseline or Drain training.

Primary commands:

- `uv run logsensing train baseline ...`
- `uv run logsensing train drain ...`

Expected outputs:

- trained artifact path
- short note describing what the artifact is for

### 4. RAG/Agent

Use when the request involves:

- `agent analyze`
- `agent chat`
- knowledge docs
- platform RAG stores
- anomalies plus supporting docs for RCA

Primary commands:

- `uv run logsensing agent analyze ...`
- `uv run logsensing agent chat ...`

Expected outputs:

- generated analysis path or terminal summary
- knowledge inputs used
- any index or store path that matters for follow-up work

### 5. Environment Repair

Use before any operational playbook when runtime readiness is uncertain.

This playbook is also invoked directly when the user asks to fix the environment.

## Execution Flow

Every run should follow the same high-level sequence:

1. Normalize user inputs.
2. Detect the correct `logsensing` repository context.
3. Check runtime readiness.
4. Apply safe auto-repair if possible.
5. Route to the correct playbook.
6. Summarize results in a compact, structured way.

## Repository and Runtime Detection

The skill should:

1. Prefer operating inside the `logsensing` repository.
2. Reuse the current working directory when it is already the repo.
3. If the user provides a repo path, switch to that path.
4. If the repo cannot be found, stop and ask for the repo location instead of guessing.

The skill should prefer `uv run logsensing ...` over direct system Python execution.

## Environment Readiness Policy

The readiness sequence should be:

1. Check that `uv` exists.
2. Check that `uv run logsensing --help` works from the repo.
3. If it fails due to missing dependencies or an unprepared environment, attempt `uv sync`.
4. Re-run `uv run logsensing --help`.

### Safe Auto-Fix Boundary

Allowed:

- `uv sync`

Not allowed:

- `pip install` into system Python
- bypassing the lockfile
- ad hoc package installation flows not documented by the repo
- silent fallbacks that hide the environment failure

If `uv sync` fails, the skill must stop and report the root cause category, such as:

- missing `uv`
- network failure
- permission problem
- lockfile or dependency resolution failure
- repository/path mismatch

## Context Budget Rules

The skill must be written to preserve room for actual log analysis.

### Required behavior

1. Prefer summaries, counts, top-N anomalies, and representative excerpts.
2. Prefer structured outputs such as `anomalies.json` and generated reports over repeatedly re-reading full raw logs.
3. Avoid pasting large raw log blocks unless they are the minimum needed to support a conclusion.
4. Keep the skill instructions short and operational, not essay-like.
5. When the user supplies a large snippet, compress it into key issue clusters, timestamps, and line-numbered highlights before deeper reasoning.

## Output Contract

Each successful run should return a compact result with:

1. A one-line conclusion.
2. The key commands or steps performed.
3. Artifact paths that were produced or reused.
4. Top anomaly rules or findings.
5. Affected cycle IDs when relevant.
6. Issue line numbers for quick lookup.
7. Timestamps when available and useful.
8. The next most relevant inspection point only when necessary.

Each failed run should return:

1. The exact command or check that failed.
2. The root cause, stated plainly.
3. The boundary that prevented further automatic action.

## Interaction Style

The skill should optimize for direct execution:

1. If enough information is present, execute immediately.
2. If information is missing, ask only for the minimum required detail.
3. Do not force long clarifying conversations before straightforward operations.
4. Do not present success-shaped output when execution actually failed.

## Deployment Model

### Repo copy

Store the source-of-truth version in the repository so the skill evolves with the project.

Recommended repo path:

`docs/superpowers/skills/logsensing/`

This directory should contain the skill definition and any helper reference material needed for maintenance.

### User copy

Install a runnable copy into the user's skill directory so Copilot can load it directly on the machine.

The repo copy remains authoritative; the user copy is a synchronized deployment artifact.

### Sync expectation

The workflow should avoid long-term drift between repo and user copies. A simple documented copy or sync step is sufficient; no separate design authority should exist in the user directory.

## Verification Strategy

The skill should be validated in four layers.

### 1. Environment verification

- `uv` present
- `uv run logsensing --help` succeeds

### 2. Routing verification

Representative prompts route correctly to:

- `analyze`
- `triage`
- `baseline_train`
- `rag_agent`
- `env_repair`

### 3. Output verification

Summaries include:

- artifact paths
- top findings
- line numbers
- root cause on failure

### 4. Safety-boundary verification

The skill stops correctly on:

- missing repo
- missing `uv`
- failed `uv sync`
- failed `logsensing` command

## Implementation Notes

1. Keep the skill model-agnostic in wording.
2. Reflect the repo's existing command names and documented workflows exactly.
3. Make line numbers part of the default issue summary, not an optional extra.
4. Keep the playbook descriptions short enough that they do not consume the analysis budget needed for logs.

## Final Recommendation

Build one `logsensing` skill with playbook-based routing, strict `uv` runtime discipline, compact structured outputs, and repo-plus-user deployment. This gives users a simple interface while keeping execution reliable and context usage controlled.
