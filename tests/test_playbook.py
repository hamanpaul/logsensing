"""Validate test-playbook artifacts under tests/playbook/."""

from __future__ import annotations

import json
from pathlib import Path

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


def _load_json_yaml(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def test_fixture_manifest_used_by_refs_known_cases() -> None:
    case_ids: set[str] = set()
    for filename in SUITE_FILES:
        data = _load_json_yaml(PLAYBOOK_DIR / filename)
        case_ids.update(case["case_id"] for case in data["cases"])

    manifest = _load_json_yaml(PLAYBOOK_DIR / "fixtures_manifest.yaml")
    for fixture in manifest["fixtures"]:
        for ref in fixture["used_by"]:
            assert ref in case_ids
