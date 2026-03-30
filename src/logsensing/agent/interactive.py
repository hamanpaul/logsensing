"""Interactive Q&A CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from logsensing.agent.rca import RCAReport


class InteractiveAgent:
    """互動式問答 Agent（規則式版本）."""

    COMMANDS: ClassVar[dict[str, str]] = {
        "help": "顯示可用命令",
        "cycles": "列出所有 boot cycles",
        "anomalies [cycle_id]": "顯示異常事件(可指定 cycle)",
        "report [cycle_id]": "產生 RCA 報告(可指定 cycle)",
        "templates": "顯示 Drain3 模板統計",
        "baseline": "顯示基準線 profile",
        "quit": "離開",
    }

    def __init__(
        self,
        anomalies_path: Path | None = None,
        baseline_path: Path | None = None,
        drain_state_path: Path | None = None,
        log_path: Path | None = None,
    ) -> None:
        self.console = Console()
        self._anomalies_data: dict[str, Any] = {}
        self._baseline_data: dict[str, Any] = {}
        self._drain_state: dict[str, Any] = {}

        if anomalies_path and anomalies_path.exists():
            self._anomalies_data = json.loads(anomalies_path.read_text(encoding="utf-8"))
        if baseline_path and baseline_path.exists():
            self._baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        if drain_state_path and drain_state_path.exists():
            self._drain_state = json.loads(drain_state_path.read_text(encoding="utf-8"))

        self._rca = RCAReport(anomalies_data=self._anomalies_data)

    def run(self) -> None:
        """Run interactive loop."""
        self.console.print("[bold green]LogSensing Interactive Agent[/bold green]")
        self.console.print("輸入 'help' 查看可用命令\n")

        while True:
            try:
                cmd = Prompt.ask("[bold blue]logsensing[/bold blue]")
                if not self._handle_command(cmd.strip()):
                    break
            except (KeyboardInterrupt, EOFError):
                break

        self.console.print("\n[dim]Bye![/dim]")

    def _handle_command(self, cmd: str) -> bool:
        """Handle a command. Return False to exit."""
        if cmd in ("quit", "exit"):
            return False
        elif cmd == "help":
            self._show_help()
        elif cmd == "cycles":
            self._show_cycles()
        elif cmd.startswith("anomalies"):
            self._show_anomalies(cmd)
        elif cmd.startswith("report"):
            self._show_report(cmd)
        elif cmd == "templates":
            self._show_templates()
        elif cmd == "baseline":
            self._show_baseline()
        else:
            self.console.print(f"[red]未知命令: {cmd}[/red]. 輸入 'help' 查看可用命令.")
        return True

    # ------------------------------------------------------------------
    # command handlers
    # ------------------------------------------------------------------

    def _show_help(self) -> None:
        lines = ["## 可用命令\n"]
        for cmd, desc in self.COMMANDS.items():
            lines.append(f"- **{cmd}** — {desc}")
        self.console.print(Markdown("\n".join(lines)))

    def _show_cycles(self) -> None:
        cycle_ids = self._rca._get_all_cycle_ids()
        if not cycle_ids:
            self.console.print("[yellow]無可用的 cycle 資料。[/yellow]")
            return
        self.console.print(f"[bold]Boot Cycles:[/bold] {', '.join(str(c) for c in cycle_ids)}")

    def _show_anomalies(self, cmd: str) -> None:
        parts = cmd.split()
        cycle_id = int(parts[1]) if len(parts) > 1 else None

        if cycle_id is not None:
            anomalies = self._rca._get_cycle_anomalies(cycle_id)
            if not anomalies:
                self.console.print(f"[yellow]Cycle #{cycle_id} 無異常事件。[/yellow]")
                return
            self.console.print(f"[bold]Cycle #{cycle_id} 異常事件 ({len(anomalies)}):[/bold]")
            for a in anomalies:
                attrs = a.get("attributes", {})
                sev = attrs.get("anomaly.severity", "info")
                name = attrs.get("anomaly.rule_name", "")
                msg = attrs.get("anomaly.message", "")
                color = self._sev_color(sev)
                self.console.print(f"  [{color}][{sev}][/{color}] {name}: {msg}")
        else:
            summary = self._anomalies_data.get("summary", {})
            total = summary.get("total_anomalies", 0)
            self.console.print(f"[bold]總異常數: {total}[/bold]")
            by_sev = summary.get("by_severity", {})
            for sev, count in by_sev.items():
                color = self._sev_color(sev)
                self.console.print(f"  [{color}]{sev}: {count}[/{color}]")

    def _show_report(self, cmd: str) -> None:
        parts = cmd.split()
        if len(parts) > 1:
            cycle_id = int(parts[1])
            md = self._rca.generate_cycle_report(cycle_id)
        else:
            md = self._rca.generate_summary_report()
        self.console.print(Markdown(md))

    def _show_templates(self) -> None:
        if not self._drain_state:
            self.console.print("[yellow]無 Drain3 模板資料。[/yellow]")
            return
        clusters = self._drain_state.get("clusters", [])
        self.console.print(f"[bold]Drain3 模板數量: {len(clusters)}[/bold]")
        for cluster in clusters[:10]:
            cid = cluster.get("cluster_id", "?")
            size = cluster.get("cluster_count", cluster.get("size", 0))
            template = cluster.get("log_template_tokens", cluster.get("template", ""))
            if isinstance(template, list):
                template = " ".join(template)
            self.console.print(f"  [{cid}] (x{size}) {template[:80]}")
        if len(clusters) > 10:
            self.console.print(f"  ... 共 {len(clusters)} 個模板")

    def _show_baseline(self) -> None:
        if not self._baseline_data:
            self.console.print("[yellow]無基準線資料。[/yellow]")
            return
        mean_deltas = self._baseline_data.get("mean_deltas", {})
        sample_count = self._baseline_data.get("sample_count", 0)
        self.console.print(f"[bold]基準線 Profile (樣本數: {sample_count}):[/bold]")
        for pair, mean in mean_deltas.items():
            stddev = self._baseline_data.get("stddev_deltas", {}).get(pair, 0.0)
            self.console.print(f"  {pair}: {mean:.3f}s ± {stddev:.3f}s")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sev_color(severity: str) -> str:
        return {"critical": "red", "warning": "yellow", "info": "blue"}.get(severity, "white")
