# LogSensing 開發計畫

## 專案定位

全自動化日誌分析 CLI 工具，針對設備 Power Cycle 壓力測試產生的巨量、多執行緒交錯日誌進行解析。
結合 Drain3 動態日誌探勘與 LLM Agent，將除錯流程從「人工搜尋」升級為「AI 自動根因診斷」。

## 技術決策

| 項目 | 決策 |
|------|------|
| 語言 | Python 3.10+ |
| 專案結構 | src layout（`src/logsensing/`） |
| 建置工具 | pyproject.toml + uv |
| CLI 框架 | Typer |
| 日誌探勘 | Drain3 |
| 異常輸出 | OpenTelemetry JSON |
| LLM 整合 | Function Calling（模型可抽換） |
| 檢索引擎 | BM25 + FAISS（進階里程碑） |

## 目前進度（2026-03-31）

- [x] Phase 1 Parser：Boot cycle 切割、Drain3 模板探勘、Demux 分流
- [x] Phase 2 Analyzer：Baseline、Anomaly Detector、OTel Exporter、Boot timing report
- [x] 多平台抽象：BDK / prplOS profile、自動偵測、sequence-only timing 分析
- [x] Phase 3 Agent：`agent analyze` / `agent chat` 已可讀 anomaly、baseline、drain state、原始 log
- [x] Sprint 4 RAG 核心：chunker / BM25 / FAISS / RRF hybrid retriever
- [x] RAG CLI 整合：`agent analyze` / `agent chat` 已可從 `--knowledge-doc` 或 config 建立/載入索引
- [x] 平台感知 RAG 記憶：依 log 自動判斷平台、載入同平台 docs/experiences、分析後自動回寫結構化經驗
- [x] 測試現況：189 tests passing，ruff clean

### RAG 整合策略

- CLI 優先讀取既有索引：`--bm25-index` / `--faiss-index`
- 若索引不存在且提供 `--knowledge-doc`（或 config `rag.knowledge_docs`），則現場切塊並建立索引
- 向量相依不存在時，自動降級為 BM25-only，保持 agent 功能可用
- `agent analyze` 與 `agent chat` 共用同一組 RAG helper，避免行為漂移
- 預設以 `.cache/logsensing/rag/<platform>/` 隔離不同平台索引與經驗，避免混庫
- `agent analyze` 只回寫結構化 RCA/證據摘要，不保存完整 raw log 或整段對話
- 回寫後會 deterministic rebuild 該平台索引，讓下次同平台分析能直接檢索既有經驗

## 樣本日誌分析

**檔案：** `docs/sample_logs/20260318_ATT_newHW7-normal_1354.log`（7MB, 113,105 行）
**裝置：** BGW720-300 (Broadcom BCM68575_B0, ARM Cortex A53 Dual Core)
**狀態：** 正常開機（無 Kernel panic / OOM）
**Boot Cycles：** 25 次（以 `U-Boot TPL` 為錨點計數）

### 日誌格式

```
[YYYY-MM-DD HH:MM:SS.mmm] <message>
```

時間戳為測試主機側（非裝置內部 uptime），毫秒精度。

### 已識別錨點字串

| 錨點 | 用途 | 出現次數 |
|------|------|----------|
| `U-Boot TPL` | Boot Cycle 切割主錨點 | 25 |
| `Starting kernel ...` | Kernel 交接 | 24 |
| `Booting Linux` | Linux 啟動 | 24 |

### 已識別開機里程碑

| 順序 | 里程碑 | 匹配模式 |
|------|--------|----------|
| 1 | TPL 啟動 | `U-Boot TPL` |
| 2 | U-Boot 主程式 | `U-Boot 2024.04` |
| 3 | Watchdog 啟動 | `WDT:   Started watchdog` |
| 4 | FIT Image 載入 | `Found FIT format U-Boot` |
| 5 | Kernel 交接 | `Starting kernel ...` |
| 6 | Linux 啟動 | `Booting Linux on physical CPU` |
| 7 | RPC Tunnel 完成 | `Init complete for FIFO tunnel` |
| 8 | PCIe Link UP | `bcm-pcie: Core .* Link UP` |
| 9 | 網路設定 | `Configuring networking...` |
| 10 | Ethernet 就緒 | `wait_enet_ready done` |
| 11 | WiFi FW 載入 | `dhd_bus_start_try download fw` |

### 已識別模組前綴（Demux 頻道）

| 模組 | 出現次數 | 分類 |
|------|----------|------|
| `wl0` / `wl1` / `wl2` | ~3,400 | WiFi |
| `RPC` | 1,150 | 跨核心 RPC |
| `SMCOS` | 1,098 | SMC OS |
| `SBF` | 781 | Switch Buffer |
| `acsd` | 507 | ACS Daemon |
| `dhd*` / `dhdpcie*` | ~600 | DHD Driver |
| `dol0` / `dol1` / `dol2` | ~495 | Offload Engine |
| `fcache` | 144 | Flow Cache |

### 已識別錯誤模式

| 模式 | 嚴重性 | 說明 |
|------|--------|------|
| `CFG80211-ERROR` | warning | WiFi vendor IE 設定錯誤（-19），每個 cycle 重複出現 |
| `bcm_sotp_ctl_perm.*error` | info | SOTP 控制不支援，U-Boot 階段正常出現 |
| `Kernel panic` | critical | 本樣本未出現（正常開機） |
| `Out of memory` / `oom` | critical | 本樣本未出現 |

## 三階段管線架構

```
Raw Log ──▶ [Phase 1: Parser] ──▶ [Phase 2: Analyzer] ──▶ [Phase 3: Agent CLI]
              │                      │                       │
              ├─ Stream Splitter     ├─ Baseline Profiling   ├─ Automated RCA
              ├─ Drain3 模板探勘     ├─ Anomaly Detection    ├─ Interactive Q&A
              └─ Demultiplexing      └─ OTel JSON 輸出       └─ RAG 檢索（進階）
```

## 開發里程碑

### Sprint 1：基礎設施與 Drain3 導入

**目標：** 實作日誌串流讀取、切割邏輯，並串接 Drain3 進行日誌模板初步訓練與解析。

- [ ] 專案骨架搭建（pyproject.toml、目錄結構、CI lint）
- [ ] Stream Splitter：以 Bootloader 錨點字串切割巨型日誌為單一 Boot Cycle 區塊
- [ ] Drain3 整合：動態模板探勘，產出模板對照表
- [ ] Demultiplexer：依 PID / 模組前綴分流至虛擬頻道
- [ ] 單元測試與整合測試基礎

**交付物：** `parser.py` 模組 + 日誌模板對照表

### Sprint 2：規則引擎與標準化輸出

**目標：** 建立時間軸運算、多執行緒分流，將異常轉為 OTel 標準 JSON。

- [ ] Baseline Profiling：計算正常開機各里程碑平均 Delta Time
- [ ] Anomaly Detector：時間容忍閥值 + 致命錯誤規則庫（Kernel panic 等）
- [ ] Context Clipper：錯誤命中後裁切前後 N 行乾淨日誌
- [ ] OTel Exporter：TraceID / SpanID 賦值，輸出 `anomalies.json`
- [ ] 規則引擎測試

**交付物：** `analyzer.py` 模組 + `anomalies.json` 樣本

### Sprint 3：CLI 封裝與 Agent 整合

**目標：** 建立命令列介面，透過 Function Calling 串接 LLM API 產出 RCA 報告。

- [x] Typer CLI 封裝（parse / analyze / agent 子命令）
- [x] LLM Agent：讀取 anomalies.json 自動撰寫 RCA 摘要
- [x] Interactive Q&A：終端機互動式問答介面
- [x] 組態管理（config.toml / 環境變數）
- [x] 端到端測試

**交付物：** `agent_cli.py` + 自動化 RCA 摘要報告

### Sprint 4：混合 RAG 知識庫

**目標：** 硬體規格書語意切塊，建立雙軌檢索引擎強化 Agent 領域知識。

- [x] 文件切塊器（Markdown / Text → chunks）
- [x] BM25 精準匹配索引
- [x] FAISS 向量語意檢索
- [x] 混合檢索 API（融合排序）
- [x] Agent 知識庫整合

**交付物：** 向量資料庫建置 + 混合檢索 API

## 專案目錄結構

```
logsensing/
├── README.md
├── pyproject.toml
├── uv.lock
├── docs/
│   ├── logsensing-agent-dev.md   # 原始開發計畫書
│   ├── plan.md                   # 本檔：開發計畫
│   ├── spec.md                   # 技術規格
│   └── todo.md                   # 開發待辦追蹤
├── src/
│   └── logsensing/
│       ├── __init__.py
│       ├── cli.py                # Typer CLI 入口
│       ├── parser/
│       │   ├── __init__.py
│       │   ├── splitter.py       # Stream Splitter
│       │   ├── drain.py          # Drain3 整合
│       │   └── demux.py          # Demultiplexer
│       ├── analyzer/
│       │   ├── __init__.py
│       │   ├── baseline.py       # Baseline Profiling
│       │   ├── detector.py       # Anomaly Detector
│       │   ├── clipper.py        # Context Clipper
│       │   └── exporter.py       # OTel Exporter
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── rca.py            # Root Cause Analysis
│       │   ├── interactive.py    # Interactive Q&A
│       │   └── rag.py            # RAG 檢索（進階）
│       └── config.py             # 組態管理
├── tests/
│   ├── conftest.py
│   ├── test_splitter.py
│   ├── test_drain.py
│   ├── test_demux.py
│   ├── test_baseline.py
│   ├── test_detector.py
│   ├── test_exporter.py
│   └── test_cli.py
└── samples/                      # 測試用日誌樣本
    └── README.md
```

## 風險與備案

| 風險 | 影響 | 備案 |
|------|------|------|
| Drain3 模板品質不足 | Phase 1 產出不可靠 | 混合 Regex 前處理 + Drain3 後處理 |
| 日誌格式跨韌體版本差異過大 | 切檔錨點失效 | 可設定多錨點 fallback 策略 |
| LLM API 延遲 / 成本 | Phase 3 體驗差 | 支援本地模型（Ollama）替代 |
| 巨型日誌 OOM | Phase 1 崩潰 | 串流處理 + 記憶體上限保護 |
