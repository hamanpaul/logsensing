"""Anomaly detector — 規則引擎與異常偵測."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import BaseModel, Field

from logsensing.analyzer.baseline import (
    TIMESTAMP_RE,
    BaselineProfile,
    CycleProfile,
)

if TYPE_CHECKING:
    from logsensing.platform.base import PlatformProfile


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class AnomalyRule(BaseModel):
    """異常偵測規則."""

    rule_id: str
    name: str
    severity: Literal["critical", "warning", "info"]
    rule_type: Literal["pattern", "timeout", "sequence"]
    pattern: str = ""
    is_regex: bool = False
    timeout_sigma: float = 3.0
    milestone_pair: str = ""
    required_milestones: list[str] = Field(default_factory=list)


class Anomaly(BaseModel):
    """偵測到的異常事件."""

    anomaly_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    cycle_id: int
    rule_id: str
    rule_name: str
    severity: Literal["critical", "warning", "info"]
    rule_type: str
    timestamp: datetime | None = None
    line_number: int = 0
    message: str = ""
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------
_UNSET = object()


class AnomalyDetector:
    """規則引擎：掃描日誌行並回報異常."""

    DEFAULT_RULES: ClassVar[list[AnomalyRule]] = [
        AnomalyRule(
            rule_id="kernel_panic",
            name="Kernel Panic",
            severity="critical",
            rule_type="pattern",
            pattern="Kernel panic",
        ),
        AnomalyRule(
            rule_id="oom_killer",
            name="OOM Killer",
            severity="critical",
            rule_type="pattern",
            pattern="Out of memory",
        ),
        AnomalyRule(
            rule_id="oops",
            name="Kernel Oops",
            severity="critical",
            rule_type="pattern",
            pattern="Oops:",
            is_regex=False,
        ),
        AnomalyRule(
            rule_id="segfault",
            name="Segmentation Fault",
            severity="critical",
            rule_type="pattern",
            pattern="segfault",
        ),
        AnomalyRule(
            rule_id="watchdog_reset",
            name="Watchdog Reset",
            severity="warning",
            rule_type="pattern",
            pattern="watchdog.*reset",
            is_regex=True,
        ),
    ]

    def __init__(
        self,
        rules: list[AnomalyRule] | None = None,
        baseline: BaselineProfile | None = None,
        context_lines_before: int = 50,
        context_lines_after: int = 50,
        *,
        ts_re: re.Pattern[str] | None | object = _UNSET,
        ts_fmt: str | None | object = _UNSET,
    ) -> None:
        self.rules = rules or list(self.DEFAULT_RULES)
        self.baseline = baseline
        self.context_lines_before = context_lines_before
        self.context_lines_after = context_lines_after
        self._ts_re: re.Pattern[str] | None = TIMESTAMP_RE if ts_re is _UNSET else ts_re  # type: ignore[assignment]
        self._ts_fmt: str | None = "%Y-%m-%d %H:%M:%S.%f" if ts_fmt is _UNSET else ts_fmt  # type: ignore[assignment]

    @classmethod
    def from_platform(
        cls,
        platform: PlatformProfile,
        baseline: BaselineProfile | None = None,
        context_lines_before: int = 50,
        context_lines_after: int = 50,
    ) -> AnomalyDetector:
        """從 PlatformProfile 建立 AnomalyDetector."""
        ts_re = re.compile(platform.timestamp_pattern) if platform.timestamp_pattern else None
        return cls(
            baseline=baseline,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            ts_re=ts_re,
            ts_fmt=platform.timestamp_format,
        )

    # ---- public API --------------------------------------------------------

    def detect(
        self,
        lines: list[str],
        cycle_id: int,
        cycle_profile: CycleProfile | None = None,
    ) -> list[Anomaly]:
        """Detect anomalies in a cycle."""
        anomalies: list[Anomaly] = []

        # 1. Pattern rules
        anomalies.extend(self._detect_patterns(lines, cycle_id))

        # 2. Timeout rules (require baseline + profile)
        if self.baseline and cycle_profile:
            anomalies.extend(self._detect_timeouts(cycle_id, cycle_profile))

        # 3. Sequence rules (require profile)
        if cycle_profile:
            anomalies.extend(self._detect_sequences(cycle_id, cycle_profile))

        return anomalies

    # ---- private helpers ---------------------------------------------------

    def _detect_patterns(self, lines: list[str], cycle_id: int) -> list[Anomaly]:
        pattern_rules = [r for r in self.rules if r.rule_type == "pattern"]
        anomalies: list[Anomaly] = []

        for idx, line in enumerate(lines):
            for rule in pattern_rules:
                matched = False
                if rule.is_regex:
                    matched = bool(re.search(rule.pattern, line))
                else:
                    matched = rule.pattern in line

                if matched:
                    ts = self._parse_timestamp(line)
                    ctx_before, ctx_after = self._clip_context(lines, idx)
                    anomalies.append(
                        Anomaly(
                            cycle_id=cycle_id,
                            rule_id=rule.rule_id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            rule_type=rule.rule_type,
                            timestamp=ts,
                            line_number=idx,
                            message=line.rstrip("\n"),
                            context_before=ctx_before,
                            context_after=ctx_after,
                        )
                    )
        return anomalies

    def _detect_timeouts(self, cycle_id: int, cycle_profile: CycleProfile) -> list[Anomaly]:
        timeout_rules = [r for r in self.rules if r.rule_type == "timeout"]
        anomalies: list[Anomaly] = []

        for rule in timeout_rules:
            pair = rule.milestone_pair
            if not pair:
                continue
            if pair not in cycle_profile.deltas:
                continue
            if pair not in self.baseline.mean_deltas:
                continue

            actual = cycle_profile.deltas[pair]
            mean = self.baseline.mean_deltas[pair]
            stddev = self.baseline.stddev_deltas.get(pair, 0.0)
            threshold = mean + rule.timeout_sigma * stddev

            if actual > threshold:
                anomalies.append(
                    Anomaly(
                        cycle_id=cycle_id,
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        rule_type=rule.rule_type,
                        message=(
                            f"{pair} took {actual:.3f}s "
                            f"(threshold {threshold:.3f}s = "
                            f"mean {mean:.3f}s + {rule.timeout_sigma}s x {stddev:.3f}s)"
                        ),
                        metadata={
                            "actual": actual,
                            "mean": mean,
                            "stddev": stddev,
                            "threshold": threshold,
                            "sigma": rule.timeout_sigma,
                        },
                    )
                )
        return anomalies

    def _detect_sequences(self, cycle_id: int, cycle_profile: CycleProfile) -> list[Anomaly]:
        seq_rules = [r for r in self.rules if r.rule_type == "sequence"]
        anomalies: list[Anomaly] = []
        hit_names = {h.milestone for h in cycle_profile.hits}

        for rule in seq_rules:
            missing = [m for m in rule.required_milestones if m not in hit_names]
            if missing:
                anomalies.append(
                    Anomaly(
                        cycle_id=cycle_id,
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        rule_type=rule.rule_type,
                        message=f"Missing milestones: {', '.join(missing)}",
                        metadata={"missing": missing},
                    )
                )
        return anomalies

    def _clip_context(self, lines: list[str], hit_index: int) -> tuple[list[str], list[str]]:
        """Return (context_before, context_after) around *hit_index*."""
        start = max(0, hit_index - self.context_lines_before)
        end = min(len(lines), hit_index + self.context_lines_after + 1)
        before = [ln.rstrip("\n") for ln in lines[start:hit_index]]
        after = [ln.rstrip("\n") for ln in lines[hit_index + 1 : end]]
        return before, after

    def _parse_timestamp(self, line: str) -> datetime | None:
        if self._ts_re is None:
            return None
        m = self._ts_re.match(line)
        if m:
            return datetime.strptime(m.group(1), self._ts_fmt)
        return None
