# LogSensing 技術規格書

## 1. 系統總覽

LogSensing 是一套三階段管線（Pipeline）日誌分析工具，處理流程：

```
原始日誌 → Parser → Analyzer → Agent CLI → RCA 報告
```

### 1.1 設計約束

- **Python 3.10+**，使用型別標註與 `match` 語法
- **串流優先**：所有 Phase 1 操作必須支援串流處理，避免將整份日誌載入記憶體
- **可插拔架構**：各模組透過明確介面解耦，便於獨立測試與替換
- **OTel 標準輸出**：異常資料採用 OpenTelemetry 語意標準

---

## 2. Phase 1：Parser & Normalizer

### 2.1 Stream Splitter

**職責：** 將巨型日誌檔按 Boot Cycle 切割為獨立區塊。

**介面定義：**

```python
@dataclass
class BootCycle:
    cycle_id: int
    start_offset: int          # 檔案位元組偏移
    end_offset: int
    start_line: int
    end_line: int
    anchor_line: str           # 觸發切割的錨點行
    timestamp_start: datetime | None
    timestamp_end: datetime | None

class StreamSplitter:
    def __init__(self, anchors: list[str], encoding: str = "utf-8"):
        """
        anchors: Bootloader 錨點字串清單（任一命中即切割）
        """
        ...

    def split(self, stream: IO[bytes]) -> Iterator[BootCycle]:
        """串流式切割，yield 每個 Boot Cycle 元資料"""
        ...

    def read_cycle(self, path: Path, cycle: BootCycle) -> Iterator[str]:
        """依 offset 讀取指定 cycle 的日誌行"""
        ...
```

**錨點策略：**
- 預設主錨點：`"U-Boot TPL"` — 實測每個 Boot Cycle 開頭首次出現
- 備用錨點：`"Starting kernel"`, `"Booting Linux"`
- 支援正則表達式錨點
- 多錨點 fallback：依序嘗試，首個命中者為準

**實測日誌格式（BGW720-300）：**
```
[YYYY-MM-DD HH:MM:SS.mmm] <message>
```
時間戳為測試主機側，毫秒精度。每行以 `[timestamp] ` 開頭。

**記憶體保護：**
- 單一 cycle 行數上限：可設定（預設 100,000 行）
- 超限時截斷並標記 `truncated=True`

### 2.2 Drain3 整合

**職責：** 動態探勘日誌模板，剝離常數模板與動態參數。

**介面定義：**

```python
@dataclass
class LogTemplate:
    template_id: int
    template: str              # 如 "eth0: link <*> speed <*>"
    count: int                 # 命中次數
    cluster_id: int

@dataclass
class ParsedLine:
    raw: str
    template_id: int
    template: str
    params: dict[str, str]     # 動態參數鍵值對
    timestamp: datetime | None
    pid: int | None
    module: str | None

class DrainParser:
    def __init__(self, config: DrainConfig | None = None):
        ...

    def parse_line(self, line: str) -> ParsedLine:
        """解析單行日誌"""
        ...

    def parse_cycle(self, lines: Iterator[str]) -> Iterator[ParsedLine]:
        """批次解析一個 cycle"""
        ...

    def get_templates(self) -> list[LogTemplate]:
        """取得目前學習到的所有模板"""
        ...

    def save_state(self, path: Path) -> None:
        """持久化 Drain3 模型狀態"""
        ...

    def load_state(self, path: Path) -> None:
        """載入已訓練的 Drain3 模型"""
        ...
```

**Drain3 組態（DrainConfig）：**

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `sim_th` | 0.4 | 模板相似度閥值 |
| `depth` | 4 | 解析樹深度 |
| `max_clusters` | 1024 | 最大叢集數量 |
| `extra_delimiters` | `[":", "=", "|"]` | 額外分隔符 |

### 2.3 Demultiplexer

**職責：** 依 PID / 模組前綴將日誌行分流至虛擬頻道。

```python
@dataclass
class Channel:
    name: str                  # 頻道名稱（如 "kernel", "networkd"）
    filter_pattern: str        # 匹配模式
    lines: list[ParsedLine]    # 屬於此頻道的日誌行

class Demultiplexer:
    def __init__(self, channel_defs: list[ChannelDef]):
        ...

    def demux(self, lines: Iterator[ParsedLine]) -> dict[str, Channel]:
        """將解析後的日誌行分配至各頻道"""
        ...
```

---

## 3. Phase 2：Rule Engine & Analyzer

### 3.1 Baseline Profiler

**職責：** 運算正常開機各里程碑的平均時間差。

```python
@dataclass
class Milestone:
    name: str                  # 里程碑名稱（如 "kernel_start", "network_ready"）
    pattern: str               # 匹配模板或正則
    expected_order: int        # 預期出現順序

@dataclass
class BaselineProfile:
    milestones: list[Milestone]
    mean_deltas: dict[str, timedelta]    # 里程碑間平均時間差
    stddev_deltas: dict[str, timedelta]  # 標準差
    sample_count: int                     # 取樣 cycle 數

class BaselineProfiler:
    def __init__(self, milestones: list[Milestone]):
        ...

    def train(self, cycles: list[list[ParsedLine]]) -> BaselineProfile:
        """從正常 cycle 訓練基準線"""
        ...

    def save(self, path: Path) -> None: ...
    def load(self, path: Path) -> None: ...
```

### 3.2 Anomaly Detector

**職責：** 套用規則庫偵測異常事件。

```python
@dataclass
class AnomalyRule:
    rule_id: str
    name: str
    severity: Literal["critical", "warning", "info"]
    rule_type: Literal["pattern", "timeout", "sequence"]
    config: dict

@dataclass
class Anomaly:
    anomaly_id: str
    cycle_id: int
    rule_id: str
    severity: str
    timestamp: datetime | None
    message: str
    context_before: list[str]  # 前 N 行
    context_after: list[str]   # 後 N 行
    metadata: dict

class AnomalyDetector:
    def __init__(self, rules: list[AnomalyRule], baseline: BaselineProfile | None = None):
        ...

    def detect(self, cycle: list[ParsedLine], cycle_id: int) -> list[Anomaly]:
        """偵測單一 cycle 中的所有異常"""
        ...
```

**內建規則類型：**

| 類型 | 說明 | 範例 |
|------|------|------|
| `pattern` | 模板/正則匹配 | Kernel panic, OOM killer |
| `timeout` | 里程碑超時 | kernel_start → network_ready > 3σ |
| `sequence` | 事件序列異常 | 缺少預期里程碑 |

### 3.3 Context Clipper

**職責：** 精準裁切案發現場前後 N 行乾淨日誌。

```python
class ContextClipper:
    def __init__(self, before: int = 50, after: int = 50):
        ...

    def clip(self, lines: list[str], hit_index: int) -> tuple[list[str], list[str]]:
        """回傳 (context_before, context_after)"""
        ...
```

### 3.4 OTel Exporter

**職責：** 將異常資料轉為 OpenTelemetry 標準 JSON。

**輸出格式（anomalies.json）：**

```json
{
  "resource": {
    "service.name": "logsensing",
    "device.model": "<device_model>"
  },
  "traces": [
    {
      "traceId": "<boot_cycle_trace_id>",
      "spans": [
        {
          "spanId": "<anomaly_span_id>",
          "name": "anomaly.kernel_panic",
          "startTimeUnixNano": 1700000000000000000,
          "attributes": {
            "anomaly.severity": "critical",
            "anomaly.rule_id": "kernel_panic_001",
            "anomaly.cycle_id": 42,
            "anomaly.message": "Kernel panic - not syncing: ...",
            "anomaly.context_before_lines": 50,
            "anomaly.context_after_lines": 50
          },
          "events": [
            {
              "name": "context",
              "attributes": {
                "log.context_before": "...",
                "log.context_after": "..."
              }
            }
          ]
        }
      ]
    }
  ]
}
```

---

## 4. Phase 3：Agent CLI

### 4.1 CLI 命令結構

```
logsensing parse   <logfile>  [--anchors ...] [--output ...]
logsensing analyze <logfile>  [--rules ...] [--baseline ...]
logsensing agent   analyze    [--cycle N] [--model ...]
logsensing agent   chat       [--model ...]
logsensing train   baseline   <logfile> [--milestones ...]
logsensing train   drain      <logfile> [--config ...]
```

### 4.2 LLM Agent

**Function Calling 工具定義：**

| Tool | 說明 |
|------|------|
| `get_anomalies(cycle_id?)` | 取得異常清單 |
| `get_cycle_context(cycle_id, line_range?)` | 取得指定 cycle 原始日誌 |
| `get_baseline()` | 取得基準線 profile |
| `get_templates()` | 取得 Drain3 模板清單 |
| `search_logs(query, cycle_id?)` | 全文搜尋日誌 |

**RCA 報告格式：**

```markdown
## Cycle #42 - Root Cause Analysis

**嚴重程度：** Critical
**異常類型：** Kernel Panic

### 時間軸
- 00:00.000 - U-Boot 啟動
- 00:03.421 - Kernel 載入
- 00:15.892 - ⚠️ eth0 driver timeout
- 00:16.001 - ❌ Kernel panic

### 根因分析
...

### 建議修復方向
...
```

### 4.3 組態管理

**config.toml 結構：**

```toml
[parser]
anchors = ["U-Boot TPL"]
fallback_anchors = ["Starting kernel", "Booting Linux"]
timestamp_pattern = '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] '
encoding = "utf-8"
max_cycle_lines = 100000

[drain]
sim_th = 0.4
depth = 4
max_clusters = 1024

[analyzer]
context_lines_before = 50
context_lines_after = 50
timeout_sigma = 3.0

[agent]
model = "gpt-4o"
api_base = ""
temperature = 0.1
max_tokens = 4096

[rag]  # 進階里程碑
chunk_size = 512
chunk_overlap = 64
faiss_index_path = ""
```

---

## 5. 非功能需求

| 項目 | 要求 |
|------|------|
| 日誌檔案大小 | 支援 > 1 GB 串流處理 |
| 單次分析 Cycle 數 | 支援 > 1000 cycles |
| 記憶體上限 | 單一 cycle 處理不超過 500 MB |
| CLI 回應時間 | parse 命令 < 60s / GB |
| 測試覆蓋率 | 核心模組 ≥ 80% |
| Python 版本 | ≥ 3.10 |

---

## 6. 相依套件

### 核心

| 套件 | 用途 |
|------|------|
| `drain3` | 日誌模板動態探勘 |
| `typer` | CLI 框架 |
| `rich` | 終端機格式化輸出 |
| `pydantic` | 資料模型驗證 |
| `opentelemetry-api` | OTel 資料結構 |

### Agent

| 套件 | 用途 |
|------|------|
| `openai` | LLM API 客戶端 |
| `httpx` | 非同步 HTTP |

### RAG（進階里程碑）

| 套件 | 用途 |
|------|------|
| `faiss-cpu` | 向量檢索 |
| `rank-bm25` | BM25 精準匹配 |
| `sentence-transformers` | 文本向量化 |

### 開發

| 套件 | 用途 |
|------|------|
| `pytest` | 測試框架 |
| `pytest-cov` | 覆蓋率 |
| `ruff` | Linter + Formatter |
| `mypy` | 靜態型別檢查 |
