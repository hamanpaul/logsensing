# LogSensing

系統日誌自動化分析與 AI 診斷工具。

針對設備 Power Cycle 壓力測試產生的巨量、多執行緒交錯日誌，結合 [Drain3](https://github.com/logpai/Drain3) 動態日誌探勘與 LLM Agent，將除錯流程從「人工搜尋」升級為「AI 自動根因診斷」。

## 功能特色

- **多平台支援** — 可擴充 PlatformProfile 架構，內建 BDK 與 prplOS 平台，自動偵測日誌來源
- **串流式日誌切割** — 以 Bootloader 錨點字串自動切割巨型日誌為單一 Boot Cycle
- **動態模板探勘** — Drain3 自動剝離常數模板與動態參數，無需維護靜態 Regex
- **多執行緒分流** — 依 PID / 模組前綴拆分至獨立虛擬頻道
- **智慧異常偵測** — 時間軸基準線比對 + 致命錯誤規則庫（pattern / timeout / sequence）
- **開機時間統計** — 自動追蹤各 process/module 啟動時序，支援無 timestamp 序列分析
- **OTel 標準輸出** — 異常資料採 OpenTelemetry 標準 JSON 格式
- **AI 根因分析** — LLM Function Calling 自動撰寫 RCA 報告（無 API 時自動 fallback 規則式報告）
- **互動式問答** — 終端機自然語言指令介面（Rich TUI）
- **混合 RAG 知識庫** — BM25 精準匹配 + FAISS 向量檢索（RRF 融合排序），自動注入 Datasheet / Release Notes 上下文

## 快速開始

### 環境需求

- Python ≥ 3.10
- [uv](https://docs.astral.sh/uv/) 套件管理工具

### 安裝

```bash
# 複製專案
git clone <repo-url>
cd logsensing

# 安裝核心相依
uv sync

# 安裝 AI Agent 相依（可選）
uv sync --extra agent

# 安裝 RAG 知識庫相依（可選）
uv sync --extra rag

# 安裝開發相依
uv sync --extra dev
```

### 基本用法

```bash
# 解析日誌，切割 Boot Cycles 並探勘模板
logsensing parse device.log --output parsed/

# 產生開機時間統計報告（自動偵測平台）
logsensing report device.log

# 指定平台
logsensing report --platform prplos serial_console.log
logsensing report --platform bdk host_captured.log

# 分析異常
logsensing analyze device.log --output anomalies.json

# 訓練 Baseline（從正常日誌）
logsensing train baseline normal.log --output baseline.json

# 訓練 Drain3 模板模型
logsensing train drain device.log --output drain_state.json

# AI 自動根因分析（需 agent 依賴 + API key）
logsensing agent analyze anomalies.json --baseline baseline.json

# 互動式問答
logsensing agent chat --anomalies anomalies.json
```

### 支援平台

| 平台 | 名稱 | 時間戳 | 說明 |
|------|------|--------|------|
| BDK | `bdk` | ✓ Host-side `[YYYY-MM-DD HH:MM:SS.mmm]` | BDK proprietary init |
| prplOS | `prplos` | ✗ Raw serial console | OpenWrt/procd init |

使用 `--platform auto`（預設）自動偵測，或以 `--platform bdk` / `--platform prplos` 手動指定。

## 架構

```
Raw Log ──▶ Phase 1: Parser ──▶ Phase 2: Analyzer ──▶ Phase 3: Agent CLI
              │                    │                      │
              ├ Stream Splitter    ├ Baseline Profiling   ├ LLM RCA (Function Calling)
              ├ Drain3 模板探勘    ├ Anomaly Detection    ├ Interactive Q&A (Rich TUI)
              └ Demultiplexing     └ OTel JSON 輸出       └ RAG 混合檢索（BM25 + FAISS）
```

## 專案結構

```
logsensing/
├── src/logsensing/
│   ├── cli.py            # Typer CLI 入口
│   ├── config.py         # Pydantic 組態管理
│   ├── parser/           # Phase 1: 日誌解析
│   │   ├── splitter.py   #   串流式 Boot Cycle 切割
│   │   ├── drain.py      #   Drain3 模板探勘
│   │   └── demux.py      #   模組前綴分流
│   ├── analyzer/         # Phase 2: 異常偵測
│   │   ├── baseline.py   #   基準線訓練與比對
│   │   ├── detector.py   #   規則式異常偵測
│   │   └── exporter.py   #   OTel JSON 匯出
│   ├── agent/            # Phase 3: AI Agent
│   │   ├── llm.py        #   OpenAI 相容 LLM 客戶端
│   │   ├── tools.py      #   Function Calling 工具定義
│   │   ├── rca.py        #   RCA 報告生成器
│   │   └── interactive.py#   互動式問答 TUI
│   └── rag/              # RAG 知識庫
│       ├── chunker.py    #   文件切塊器
│       ├── bm25.py       #   BM25 精準匹配索引
│       ├── vector.py     #   FAISS 向量檢索索引
│       └── retriever.py  #   混合檢索 API（RRF 融合）
├── tests/                # 測試（143 tests）
├── docs/                 # 文件
└── samples/              # 測試用日誌樣本
```

## 開發

```bash
# 安裝所有相依（含 dev + agent + rag）
uv sync --extra dev --extra agent --extra rag

# 執行測試
uv run pytest

# Lint & Format
uv run ruff check .
uv run ruff format .

# 型別檢查
uv run mypy src/
```

## 文件

- [開發計畫](docs/plan.md)
- [技術規格](docs/spec.md)
- [待辦追蹤](docs/todo.md)
- [原始開發計畫書](docs/logsensing-agent-dev.md)

## 授權

MIT
