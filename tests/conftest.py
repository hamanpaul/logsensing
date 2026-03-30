"""LogSensing 測試共用 fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

SAMPLE_LOG_DIR = Path(__file__).parent.parent / "docs" / "sample_logs"
SAMPLE_LOG = SAMPLE_LOG_DIR / "20260318_ATT_newHW7-normal_1354.log"


@pytest.fixture
def sample_log_path() -> Path:
    """回傳樣本日誌路徑."""
    return SAMPLE_LOG


@pytest.fixture
def sample_lines() -> list[str]:
    """回傳樣本日誌前 500 行."""
    if SAMPLE_LOG.exists():
        with open(SAMPLE_LOG, encoding="utf-8") as f:
            return [next(f) for _ in range(500)]
    return []


@pytest.fixture
def single_cycle_lines() -> list[str]:
    """回傳一個完整 boot cycle 的日誌行（第 2 個 cycle，約 lines 3275-8434）."""
    if SAMPLE_LOG.exists():
        with open(SAMPLE_LOG, encoding="utf-8") as f:
            lines = f.readlines()
        return lines[3274:8434]
    return []
