"""AAAK-style compact summaries for log templates and experiences."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from logsensing.parser.drain import LogTemplate
    from logsensing.rag.memory import ExperienceArtifact

DEFAULT_ENTITY_MAP: dict[str, str] = {
    "wifi": "WFI",
    "wl0": "WFI",
    "wl1": "WFI",
    "wl2": "WFI",
    "acsd": "WFI",
    "hostapd": "WFI",
    "dhd": "DHD",
    "dhdpcie": "DHD",
    "rpc": "RPC",
    "armtf rpc": "RPC",
    "pcie": "PCI",
    "pci": "PCI",
    "bcm-pcie": "PCI",
    "kernel": "KRN",
    "smcos": "KRN",
    "sbf": "KRN",
    "printk": "KRN",
    "kfence": "KRN",
    "offload": "OFL",
    "dol0": "OFL",
    "dol1": "OFL",
    "dol2": "OFL",
    "fcache": "OFL",
    "network": "NET",
    "br0": "NET",
    "ipv6": "NET",
}

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
NORMALIZE_RE = re.compile(r"[^A-Za-z0-9]+")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "boot",
        "by",
        "complete",
        "done",
        "error",
        "for",
        "from",
        "init",
        "initialized",
        "is",
        "log",
        "module",
        "not",
        "on",
        "service",
        "system",
        "the",
        "to",
        "with",
    }
)


class AAAKLogCompressor:
    """Generate compact, LLM-readable summaries for LogSensing artifacts."""

    format_name = "aaak-log-v1"

    def __init__(
        self,
        entity_map: dict[str, str] | None = None,
        *,
        max_summary_items: int = 5,
    ) -> None:
        merged_map = {
            self._normalize_key(key): value.upper()
            for key, value in DEFAULT_ENTITY_MAP.items()
        }
        if entity_map:
            merged_map.update(
                {
                    self._normalize_key(key): value.upper()
                    for key, value in entity_map.items()
                    if key.strip() and value.strip()
                }
            )
        self._entity_map = merged_map
        self._max_summary_items = max(max_summary_items, 1)

    def compress_templates(self, templates: Sequence[LogTemplate]) -> str:
        """Compress top templates into a compact AAAK-style text block."""
        if not templates:
            return ""

        lines = [
            f"TPLSET|fmt={self.format_name}|count={min(len(templates), self._max_summary_items)}"
        ]
        ranked = sorted(
            templates,
            key=lambda template: (template.count, template.template_id),
            reverse=True,
        )
        for template in ranked[: self._max_summary_items]:
            lines.append(self._format_template(template.template, count=template.count))
        return "\n".join(lines)

    def compress_experience(self, artifact: ExperienceArtifact) -> str:
        """Compress one experience artifact into a compact text representation."""
        affected_cycles = ",".join(
            str(cycle) for cycle in artifact.summary.get("affected_cycles", []) if cycle is not None
        ) or "-"
        lines = [
            (
                f"EXP|fmt={self.format_name}|plat={artifact.platform}|"
                f"model={self._clean_value(artifact.device_model)}|"
                f"anom={artifact.summary.get('total_anomalies', 0)}|"
                f"sev={artifact.summary.get('highest_severity', 'unknown')}|"
                f"cycles={affected_cycles}"
            )
        ]

        for finding in artifact.findings[: self._max_summary_items]:
            lines.append(self._format_finding(finding))

        top_templates = artifact.evidence.get("top_templates", [])
        for template in top_templates[: self._max_summary_items]:
            if isinstance(template, str) and template.strip():
                lines.append(self._format_template(template, count=None))

        short_summary = artifact.rca.get("short_summary", "")
        if isinstance(short_summary, str) and short_summary.strip():
            lines.append(
                f'RCA|{self._infer_entity(short_summary)}|"{self._compact_quote(short_summary)}"'
            )

        return "\n".join(lines)

    def _format_finding(self, finding: dict[str, Any]) -> str:
        message = self._clean_value(str(finding.get("message", "")))
        rule_id = self._clean_value(str(finding.get("rule_id", "unknown")))
        severity = self._clean_value(str(finding.get("severity", "info")))
        cycle_id = self._clean_value(str(finding.get("cycle_id", "?")))
        line_number = self._clean_value(str(finding.get("line_number", 0)))
        entity = self._infer_entity(" ".join([rule_id, message]))
        quote = self._compact_quote(message)
        return (
            f'F|{entity}|sev={severity}|rule={rule_id}|cycle={cycle_id}|'
            f'line={line_number}|"{quote}"'
        )

    def _format_template(self, template_text: str, *, count: int | None) -> str:
        entity = self._infer_entity(template_text)
        keyword = self._extract_keyword_code(template_text)
        count_part = f"|hit={count}" if count is not None else ""
        return (
            f'TPL|{entity}{count_part}|kw={keyword}|"{self._compact_quote(template_text)}"'
        )

    def _infer_entity(self, text: str) -> str:
        lowered = text.lower()
        for key in sorted(self._entity_map, key=len, reverse=True):
            if key and key in lowered:
                return self._entity_map[key]

        match = TOKEN_RE.search(text)
        if match is None:
            return "UNK"
        token = NORMALIZE_RE.sub("", match.group(0)).upper()
        if not token:
            return "UNK"
        return token[:3]

    def _extract_keyword_code(self, text: str) -> str:
        keywords: list[str] = []
        for token in TOKEN_RE.findall(text.lower()):
            if token == "<*>":
                continue
            if token in STOPWORDS:
                continue
            normalized = token.strip("_-")
            if not normalized or normalized in keywords:
                continue
            keywords.append(normalized)
            if len(keywords) == 2:
                break
        return "_".join(keywords) or "generic"

    def _compact_quote(self, text: str, *, limit: int = 72) -> str:
        collapsed = " ".join(text.replace("<*>", "*").split())
        return self._clean_value(collapsed)[:limit]

    def _clean_value(self, value: str) -> str:
        return value.replace('"', "'").strip()

    def _normalize_key(self, key: str) -> str:
        return " ".join(key.lower().split())
