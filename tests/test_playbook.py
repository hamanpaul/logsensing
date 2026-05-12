"""Validate test-playbook artifacts under tests/playbook/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLAYBOOK_DIR = Path(__file__).parent / "playbook"
SUITE_FILES = [
    "parser_cases.yaml",
    "analyzer_cases.yaml",
    "reporter_cases.yaml",
    "platform_cases.yaml",
    "agent_cases.yaml",
]
REQUIRED_CASE_KEYS = {
    "case_id",
    "title",
    "purpose",
    "inputs",
    "steps",
    "expected",
    "priority",
    "automation",
    "current_refs",
}


def _load_json_yaml(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_used_by_entries(
    used_by: list[dict[str, Any]],
    case_ids: set[str],
) -> None:
    seen_case_ids: set[str] = set()

    for entry in used_by:
        assert isinstance(entry, dict)
        assert {"case_id", "kind"} <= set(entry)

        case_id = entry["case_id"]
        kind = entry["kind"]

        assert isinstance(case_id, str)
        assert case_id
        assert case_id not in seen_case_ids
        seen_case_ids.add(case_id)

        assert kind in {"existing", "planned"}
        if kind == "existing":
            assert case_id in case_ids

        if "notes" in entry:
            assert isinstance(entry["notes"], str)


def test_playbook_files_exist() -> None:
    expected = {
        "parser_cases.yaml",
        "analyzer_cases.yaml",
        "reporter_cases.yaml",
        "platform_cases.yaml",
        "agent_cases.yaml",
        "coverage_matrix.yaml",
        "fixtures_manifest.yaml",
    }
    actual = {path.name for path in PLAYBOOK_DIR.glob("*.yaml")}
    assert expected <= actual


def test_suite_case_schema_and_uniqueness() -> None:
    seen_case_ids: set[str] = set()

    for filename in SUITE_FILES:
        data = _load_json_yaml(PLAYBOOK_DIR / filename)
        assert "suite" in data
        assert "cases" in data
        assert isinstance(data["cases"], list)
        assert data["cases"], f"{filename} should contain at least one case"

        for case in data["cases"]:
            assert set(case) >= REQUIRED_CASE_KEYS, f"missing keys in {filename}: {case}"
            assert case["case_id"] not in seen_case_ids, f"duplicate case_id: {case['case_id']}"
            seen_case_ids.add(case["case_id"])
            assert case["priority"] in {"p0", "p1", "p2"}
            assert case["automation"] in {"existing", "new", "manual-assisted"}
            assert isinstance(case["inputs"], list)
            assert isinstance(case["steps"], list)
            assert isinstance(case["expected"], list)
            assert isinstance(case["current_refs"], list)


def test_coverage_matrix_refs_known_suites() -> None:
    data = _load_json_yaml(PLAYBOOK_DIR / "coverage_matrix.yaml")
    suites = {entry["suite"] for entry in data["coverage"]}
    assert suites == {"parser", "analyzer", "reporter", "platform", "agent"}


def test_fixture_manifest_allows_planned_refs_without_suite_match() -> None:
    case_ids = {"platform-auto-detect", "reporter-prplos-sequence-only"}
    used_by = [
        {"case_id": "platform-auto-detect", "kind": "existing"},
        {
            "case_id": "cli-analyze-prplos-known-anomalies",
            "kind": "planned",
            "notes": "awaiting playbook case",
        },
    ]

    _validate_used_by_entries(used_by, case_ids)


def test_fixture_manifest_used_by_refs_known_cases() -> None:
    case_ids: set[str] = set()
    for filename in SUITE_FILES:
        data = _load_json_yaml(PLAYBOOK_DIR / filename)
        case_ids.update(case["case_id"] for case in data["cases"])

    manifest = _load_json_yaml(PLAYBOOK_DIR / "fixtures_manifest.yaml")
    for fixture in manifest["fixtures"]:
        assert isinstance(fixture["used_by"], list)
        _validate_used_by_entries(fixture["used_by"], case_ids)
