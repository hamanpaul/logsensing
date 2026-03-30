"""DrainParser 單元測試."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from logsensing.parser.drain import DrainParser, LogTemplate, ParsedLine

SAMPLE_LOG = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "sample_logs"
    / "20260318_ATT_newHW7-normal_1354.log"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def parser() -> DrainParser:
    return DrainParser(sim_th=0.4, depth=4)


# ---------------------------------------------------------------------------
# 1. 單行解析
# ---------------------------------------------------------------------------

class TestParseSingleLine:
    def test_basic_parse(self, parser: DrainParser) -> None:
        line = "[2026-03-18 13:54:42.819] printenv"
        result = parser.parse_line(line)

        assert isinstance(result, ParsedLine)
        assert result.raw == line
        assert result.content == "printenv"
        assert result.template_id >= 1
        assert result.line_number == 0

    def test_line_number_passed_through(self, parser: DrainParser) -> None:
        result = parser.parse_line("[2026-03-18 13:54:42.819] hello", line_number=42)
        assert result.line_number == 42


# ---------------------------------------------------------------------------
# 2. 時間戳擷取
# ---------------------------------------------------------------------------

class TestTimestamp:
    def test_valid_timestamp(self, parser: DrainParser) -> None:
        ts, content = parser._strip_timestamp("[2026-03-18 13:54:42.819] some msg")
        assert ts == datetime(2026, 3, 18, 13, 54, 42, 819000)
        assert content == "some msg"

    def test_no_timestamp(self, parser: DrainParser) -> None:
        ts, content = parser._strip_timestamp("no bracket here")
        assert ts is None
        assert content == "no bracket here"

    def test_timestamp_in_parsed_line(self, parser: DrainParser) -> None:
        result = parser.parse_line("[2026-03-18 13:55:26.478] SMCOS: rebooting system...")
        assert result.timestamp is not None
        assert result.timestamp.year == 2026
        assert result.timestamp.month == 3
        assert result.timestamp.second == 26


# ---------------------------------------------------------------------------
# 3. 模組擷取
# ---------------------------------------------------------------------------

class TestModuleExtraction:
    @pytest.mark.parametrize(
        ("content", "expected_module"),
        [
            ("RPC: initializing rpc_init service", "RPC"),
            ("wl0: some wifi message", "wl0"),
            ("acsd: channel selection done", "acsd"),
            ("SMCOS: rebooting system...", "SMCOS"),
        ],
    )
    def test_known_modules(self, parser: DrainParser, content: str, expected_module: str) -> None:
        module, remaining = parser._extract_module(content)
        assert module == expected_module
        assert remaining  # should have remaining content

    def test_no_module(self, parser: DrainParser) -> None:
        module, remaining = parser._extract_module("printenv")
        assert module is None
        assert remaining == "printenv"

    def test_module_in_parsed_line(self, parser: DrainParser) -> None:
        result = parser.parse_line("[2026-03-18 13:55:35.815] RPC: initializing rpc_init service")
        assert result.module == "RPC"


# ---------------------------------------------------------------------------
# 4. 模板學習 — 同樣 pattern 的行送入後模板穩定
# ---------------------------------------------------------------------------

class TestTemplateLearning:
    def test_template_converges(self, parser: DrainParser) -> None:
        lines = [
            "[2026-03-18 13:55:35.815] RPC: initializing rpc_init service",
            "[2026-03-18 13:55:35.815] RPC: initializing rpc_ba service",
            "[2026-03-18 13:55:35.868] RPC: initializing rpc_foo service",
        ]
        results: list[ParsedLine] = []
        for line in lines:
            results.append(parser.parse_line(line))

        # After enough similar lines, the template should contain <*>
        templates = parser.get_templates()
        assert len(templates) >= 1

        # Find the RPC template
        rpc_templates = [t for t in templates if "initializing" in t.template]
        assert rpc_templates, "Should have an RPC initializing template"
        rpc_t = rpc_templates[0]
        assert "<*>" in rpc_t.template
        assert rpc_t.count >= 2

    def test_params_extracted_after_learning(self, parser: DrainParser) -> None:
        parser.parse_line("[2026-03-18 13:55:35.815] RPC: initializing rpc_init service")
        parser.parse_line("[2026-03-18 13:55:35.815] RPC: initializing rpc_ba service")
        result = parser.parse_line("[2026-03-18 13:55:35.868] RPC: initializing rpc_foo service")

        # After template converges, params should be extracted
        if "<*>" in result.template:
            assert len(result.params) >= 1

    def test_get_templates_returns_log_template(self, parser: DrainParser) -> None:
        parser.parse_line("[2026-03-18 13:54:42.819] printenv")
        templates = parser.get_templates()
        assert len(templates) >= 1
        t = templates[0]
        assert isinstance(t, LogTemplate)
        assert t.template_id >= 1
        assert t.count >= 1


# ---------------------------------------------------------------------------
# 5. save / load state roundtrip
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_load_roundtrip(self, parser: DrainParser, tmp_path: Path) -> None:
        # Train with a few lines
        parser.parse_line("[2026-03-18 13:55:35.815] RPC: initializing rpc_init service")
        parser.parse_line("[2026-03-18 13:55:35.815] RPC: initializing rpc_ba service")

        state_file = tmp_path / "drain_state.json"
        parser.save_state(state_file)
        assert state_file.exists()

        # Load into a fresh parser
        parser2 = DrainParser(sim_th=0.4, depth=4)
        parser2.load_state(state_file)

        templates_orig = parser.get_templates()
        templates_loaded = parser2.get_templates()

        assert len(templates_loaded) == len(templates_orig)
        for t1, t2 in zip(templates_orig, templates_loaded, strict=True):
            assert t1.template == t2.template
            assert t1.count == t2.count


# ---------------------------------------------------------------------------
# 6. 使用實際 sample log(如果檔案存在)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not SAMPLE_LOG.exists(), reason="Sample log not found")
class TestWithSampleLog:
    def test_parse_first_100_lines(self, parser: DrainParser) -> None:
        with SAMPLE_LOG.open(encoding="utf-8", errors="replace") as f:
            lines = [next(f) for _ in range(100)]

        results = list(parser.parse_lines(iter(lines)))
        assert len(results) > 0

        # Every result should have a template_id (content may be empty for blank lines)
        for r in results:
            assert r.template_id >= 1

    def test_smcos_module_detected(self, parser: DrainParser) -> None:
        with SAMPLE_LOG.open(encoding="utf-8", errors="replace") as f:
            lines = list(f)

        smcos_lines = [line for line in lines if "SMCOS:" in line][:10]
        assert smcos_lines, "Sample log should contain SMCOS lines"

        for line in smcos_lines:
            result = parser.parse_line(line.rstrip())
            assert result.module == "SMCOS"

    def test_parse_lines_iterator(self, parser: DrainParser) -> None:
        with SAMPLE_LOG.open(encoding="utf-8", errors="replace") as f:
            lines = [next(f) for _ in range(50)]

        results = list(parser.parse_lines(iter(lines)))
        assert all(r.line_number >= 1 for r in results)
        # Line numbers should be sequential
        line_numbers = [r.line_number for r in results]
        assert line_numbers == sorted(line_numbers)
