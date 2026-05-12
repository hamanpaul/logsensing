# Playbook Manifest Extensibility Design

## Problem

`tests/playbook/fixtures_manifest.yaml` currently uses `used_by` as a strict list of already-existing playbook case IDs. That makes the metadata internally consistent, but it cannot represent planned or template cases without breaking `tests/test_playbook.py`.

## Goal

Allow fixture metadata to reference both implemented and planned playbook cases without weakening the existing consistency guarantees for already-landed cases.

## Non-Goals

1. Adding a new playbook suite type.
2. Treating planned cases as covered automation.
3. Introducing long-term dual-schema compatibility.

## Chosen Design

Keep a single `used_by` field, but change its schema from `string[]` to typed entry objects:

```json
{
  "case_id": "platform-auto-detect",
  "kind": "existing"
}
```

```json
{
  "case_id": "cli-analyze-prplos-known-anomalies",
  "kind": "planned",
  "notes": "awaiting playbook case"
}
```

### Entry schema

- `case_id: string` — required
- `kind: "existing" | "planned"` — required
- `notes: string` — optional

## Validation Rules

`tests/test_playbook.py` will validate `used_by` with these rules:

1. Every entry must be an object containing `case_id` and `kind`.
2. `case_id` must be a non-empty string.
3. `kind` must be either `existing` or `planned`.
4. `kind=existing` entries must match a real `case_id` from the five declared suite files.
5. `kind=planned` entries do not need to exist yet, but they must still satisfy schema rules.
6. Duplicate `case_id` values within the same fixture are invalid, regardless of kind.

## Coverage Matrix Semantics

`coverage_matrix.yaml` remains a record of implemented coverage only.

- `existing_case_ids` continues to list landed cases.
- `gaps` continues to describe uncovered work.
- `planned` fixture refs do not count as implemented coverage and are not copied into `existing_case_ids`.

## Migration

This change is a direct schema migration, not a dual-track rollout.

1. Convert all current `used_by` string entries to objects.
2. Mark currently real suite refs as `existing`.
3. Mark known future/template refs as `planned`.
4. Update validation tests to enforce the new typed-entry rules.

For the current failing fixture:

- `reporter-prplos-sequence-only` → `existing`
- `platform-auto-detect` → `existing`
- `analyzer-prplos-known-anomalies` → `planned`
- `cli-analyze-prplos-known-anomalies` → `planned`

## Why This Design

This keeps `used_by` as the single place where fixture-to-case relationships live, which preserves the mental model of the manifest. At the same time, it keeps the old consistency check meaningful by applying strict validation only to `existing` entries instead of turning the whole field into free-form notes.

## Success Criteria

1. The full test suite returns to green.
2. Fixture metadata can keep future/template refs without failing validation.
3. Implemented coverage stays distinguishable from planned coverage.
4. No second compatibility field such as `planned_used_by` or `used_by_v2` is introduced.
