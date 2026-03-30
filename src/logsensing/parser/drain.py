"""DrainParser — 基於 Drain3 的日誌模板探勘與參數擷取模組."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import jsonpickle
from drain3.template_miner import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig


@dataclass
class LogTemplate:
    """已學習到的日誌模板."""

    template_id: int
    template: str  # e.g. "RPC initializing <*> service"
    count: int  # hit count
    cluster_id: int


@dataclass
class ParsedLine:
    """單行日誌的解析結果."""

    raw: str  # 原始行(含時間戳前綴)
    content: str  # 訊息部分(去除時間戳前綴)
    template_id: int
    template: str
    params: list[str] = field(default_factory=list)  # 動態參數
    timestamp: datetime | None = None
    pid: int | None = None
    module: str | None = None
    line_number: int = 0


class DrainParser:
    """整合 Drain3 進行日誌模板探勘與參數擷取."""

    TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]\s*")
    MODULE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*(?:\d+)?)\s*:")

    def __init__(
        self,
        sim_th: float = 0.4,
        depth: int = 4,
        max_clusters: int = 1024,
        extra_delimiters: list[str] | None = None,
    ) -> None:
        """初始化 Drain3 TemplateMiner."""
        config = TemplateMinerConfig()
        config.drain_sim_th = sim_th
        config.drain_depth = depth
        config.drain_max_clusters = max_clusters
        config.drain_extra_delimiters = extra_delimiters or [":", "=", "|"]
        config.profiling_enabled = False

        self._config = config
        self._miner = TemplateMiner(config=config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_line(self, line: str, line_number: int = 0) -> ParsedLine:
        """解析單行日誌.

        步驟:
        1. 擷取時間戳
        2. 取得訊息本體（content）
        3. 擷取模組前綴
        4. 送入 Drain3 進行模板探勘
        5. 比對模板與原始內容以萃取動態參數
        """
        timestamp, content = self._strip_timestamp(line)
        module, _ = self._extract_module(content)

        result = self._miner.add_log_message(content)
        template: str = result["template_mined"]
        cluster_id: int = result["cluster_id"]

        params = self._extract_params(content, template)

        return ParsedLine(
            raw=line,
            content=content,
            template_id=cluster_id,
            template=template,
            params=params,
            timestamp=timestamp,
            module=module,
            line_number=line_number,
        )

    def parse_lines(self, lines: Iterator[str]) -> Iterator[ParsedLine]:
        """逐行解析，產生 ParsedLine."""
        for idx, line in enumerate(lines, start=1):
            stripped = line.rstrip("\n\r")
            if stripped:
                yield self.parse_line(stripped, line_number=idx)

    def get_templates(self) -> list[LogTemplate]:
        """回傳目前所有已學習的模板."""
        return [
            LogTemplate(
                template_id=cluster.cluster_id,
                template=cluster.get_template(),
                count=cluster.size,
                cluster_id=cluster.cluster_id,
            )
            for cluster in self._miner.drain.clusters
        ]

    def save_state(self, path: Path) -> None:
        """將 Drain3 模型狀態以 jsonpickle 持久化至檔案."""
        state = jsonpickle.encode(self._miner.drain, keys=True)
        path.write_text(state, encoding="utf-8")

    def load_state(self, path: Path) -> None:
        """從檔案載入先前訓練的 Drain3 模型."""
        state = path.read_text(encoding="utf-8")
        self._miner.drain = jsonpickle.decode(state, keys=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _strip_timestamp(self, line: str) -> tuple[datetime | None, str]:
        """去除時間戳前綴，回傳 (timestamp, content)."""
        m = self.TIMESTAMP_RE.match(line)
        if m:
            ts_str = m.group(1)
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
            content = line[m.end() :]
            return ts, content
        return None, line

    def _extract_module(self, content: str) -> tuple[str | None, str]:
        """擷取模組前綴，回傳 (module, remaining_content)."""
        m = self.MODULE_RE.match(content)
        if m:
            module = m.group(1)
            remaining = content[m.end() :].lstrip()
            return module, remaining
        return None, content

    def _extract_params(self, content: str, template: str) -> list[str]:
        """比對模板與原始內容，萃取 <*> 對應的動態參數."""
        content_tokens = self._tokenize(content)
        template_tokens = template.split()
        params: list[str] = []
        if len(content_tokens) != len(template_tokens):
            return params
        for ct, tt in zip(content_tokens, template_tokens, strict=True):
            if tt == "<*>":
                params.append(ct)
        return params

    def _tokenize(self, content: str) -> list[str]:
        """以與 Drain3 相同的方式切分 token（替換 extra_delimiters 為空白後 split）."""
        text = content.strip()
        for delim in self._config.drain_extra_delimiters:
            text = text.replace(delim, " ")
        return text.split()
