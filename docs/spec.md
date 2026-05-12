# LogSensing 技術規格書

> 文件定位：本文件同時描述 **目前已實作基線** 與 **AAAK / TurboQuant 增量規劃**。凡標示為「規劃新增」者，代表尚未落地到 source code，不應被視為現況功能。

## 1. 文件目標

LogSensing 目前已具備完整的三階段日誌分析管線：

1. **Parser**：切割 boot cycle、Drain3 模板探勘、模組分流
2. **Analyzer**：baseline、規則式異常偵測、OTel JSON 輸出
3. **Agent + RAG**：LLM RCA、互動式問答、BM25 + FAISS 混合檢索、platform-scoped experience writeback

本次規格增量的目標，是在不破壞既有行為下，為後續導入兩個能力建立明確邊界：

- **AAAK**：作為 parser / experience 的可選式壓縮摘要能力
- **TurboQuant**：作為 RAG 向量壓縮後端的論文導向實作方向

## 2. 現況基線

### 2.1 已實作能力

| Surface | 目前行為 | 主要檔案 |
|---|---|---|
| Parser | `StreamSplitter` 切 boot cycle；`DrainParser` 產生 `ParsedLine` / `LogTemplate`；`Demultiplexer` 依 module 分流；AAAK 可選輸出 `templates.aaak` 模板摘要 | `src/logsensing/parser/splitter.py` `src/logsensing/parser/drain.py` `src/logsensing/parser/demux.py` `src/logsensing/parser/aaak.py` |
| Analyzer | baseline profiling、pattern/timeout/sequence anomaly detection、OTel exporter，並支援平台特定 signature rule（含 prplOS b-log 常見 boot/storage/wifi error） | `src/logsensing/analyzer/` `src/logsensing/platform/prplos.py` |
| Agent | `agent analyze`、`agent chat`、LLM fallback | `src/logsensing/agent/` |
| RAG | `DocumentChunker`、`BM25Index`、`VectorIndex`、`TurboQuantVectorIndex`、`HybridRetriever`、platform experience writeback，並支援 **compact experience 優先讀取** 與可切換向量 backend | `src/logsensing/rag/chunker.py` `bm25.py` `vector.py` `turboquant.py` `retriever.py` `memory.py` |
| Config | 目前已有 parser / drain / analyzer / agent / rag 組態，且已加入 AAAK 相關設定、compact experience 讀取偏好，以及 vector backend 相關設定 | `src/logsensing/config.py` |

### 2.2 已知現況限制

1. `TurboQuantVectorIndex` 已落地基礎版，但仍缺 golden query benchmark、資源量測與預設開啟判準；預設 backend 仍為 `faiss`。
2. `ExperienceArtifact` 已可額外輸出 AAAK-style compact summary，`parse` 也可額外輸出 `templates.aaak`；`analyze` 與 Agent prompt 尚未直接使用 parser summary。
3. 已有 AAAK feature flag、compact experience 讀取偏好，以及向量 backend 切換設定；但完整 quality-gate 與 benchmark 設定尚未落地。
4. README 與既有 docs 仍需持續區分「目前已實作」與「後續規劃」。

## 3. 規格增量目標

### 3.1 AAAK 導入目標

AAAK 在本專案中的定位，不是用來取代 raw log，而是提供一層 **可選的結構化摘要**，優先應用於：

- parser 產出的模板摘要
- `ExperienceArtifact` 的壓縮版本（**基礎版已落地**）
- RAG 上下文與 LLM context window 的 token 壓縮

目前已落地範圍：

- `AAAKLogCompressor`
- `ExperienceArtifact.compact_summary`
- `.aaak` compact 檔案持久化
- `parse` 指令輸出 `templates.aaak` 模板摘要
- `rag.prefer_compact_experience = true` 時，RAG 會優先讀 compact experience

尚未落地範圍：

- `analyze` 指令直接輸出 AAAK parser summary
- AAAK summary 作為 Agent prompt 的預設輸入

### 3.2 TurboQuant 導入目標

TurboQuant 在本專案中的定位，不是直接引用外部 GPL repo，而是：

- 萃取論文核心技術與資料流設計
- 重新實作本專案可接受的向量壓縮後端
- 保持與既有 `VectorIndex.search()` / `HybridRetriever` 相容

### 3.3 授權與來源邊界

| 主題 | 規格要求 |
|---|---|
| AAAK | 研究可參考 `mempalace` 的格式與思路；若採納 code pattern，需保持與本專案 MIT 邊界相容 |
| TurboQuant | **只取論文核心技術**；GitHub GPL-3.0 repo 只作為理解基礎，不可直接移植、複製或 vendor 進本 repo |
| 文件表述 | 必須明講「paper-derived / paper-only implementation」，避免產生授權污染誤解 |

## 4. 功能需求

### 4.1 AAAK（已落地基礎版，後續擴充）

#### FR-A01：可選式 AAAK 摘要壓縮

- 系統應可在 parser / experience 後處理階段，將 `LogTemplate` 或 `ExperienceArtifact` 轉成 compact summary。
- 預設必須維持 **關閉**，不影響現行 `parse` / `analyze` / `agent` 行為。

#### FR-A02：entity code 需來自本域語意

- entity code 應優先從現有 module / channel 語意導出，例如 `RPC`、`wl0`、`SMCOS`。
- 不可直接沿用以人物/情緒為核心的原始 AAAK 欄位；需轉成 LogSensing 領域欄位，如 severity、rule type、top templates。

#### FR-A03：raw path 必須保留

- raw template、raw evidence、原始 Markdown writeback 仍是 canonical path。
- AAAK summary 僅作為額外產物或可替換的 context input，不得覆蓋 raw artifact。

#### FR-A04：AAAK 壓縮必須可回退

- 若關閉 feature flag、摘要價值不足，或品質驗證不過，系統應回退到既有 raw text path。

#### FR-A05：experience writeback 應能同時保存人類版與壓縮版

- 現有 `ExperienceArtifact.to_markdown()` 不應被破壞。
- 可新增 `to_aaak()`、`to_compact_text()` 或等價介面，但需在 spec / code / docs 使用同一命名。

### 4.2 TurboQuant（已落地基礎版，後續驗證）

#### FR-T01：向量壓縮後端需與現行檢索介面相容

- 壓縮後端應可被 `HybridRetriever` 視為與 `VectorIndex` 等價的 search provider。
- 若採新類別，介面至少需支援 `build()`、`search()`、`save()`、`load()`。

#### FR-T02：壓縮實作需以論文核心技術為邊界

- 允許採用 paper-derived rotation / quantization / residual correction 思路。
- 不允許直接搬運 GPL-3.0 repo 內的 Python 或 C/Metal 實作。

#### FR-T03：需要明確 fallback

- 若壓縮後端不可用、驗證失敗、或 quality gate 未達標，系統需回退到現有 float32 `VectorIndex`。
- 若向量依賴缺失，仍應維持目前已存在的 BM25-only 降級行為。

#### FR-T04：持久化格式需可識別 backend 與參數

- `save()` / `load()` 的 metadata 必須包含 backend 型別、bit width、embedding dimension、版本資訊。
- 讀取 metadata 時若 backend 不相容，需能拒絕載入或回退重建，不可默默產生錯誤結果。

#### FR-T05：品質驗證先於預設開啟

- 在 golden query / representative docs 上，需先驗證 retrieval quality 與資源使用，再決定是否開啟預設壓縮。

### 4.3 CLI / Docs / Workflow（規劃新增）

#### FR-C01：CLI 介面預設保持相容

- 既有 `logsensing parse/analyze/agent/train/report` 指令語意不應因新增壓縮能力而破壞。
- 優先透過 config 或內部 wiring 啟用新能力，避免一開始就擴大 CLI surface。

#### FR-C02：文件必須區分「現況」與「規劃」

- `docs/spec.md`、`docs/test.md`、`docs/plan.md`、`docs/task.md`、`docs/todo.md` 必須同步標示哪些部分尚未實作。
- README 的文件索引必須包含新增文件。

#### FR-C03：/fleet、/agent、/review、commit workflow 必須可從文件直接操作

- `docs/plan.md`：定義 lane / branch / merge gate
- `docs/test.md`：定義 `/agent` 測試執行與回報
- `docs/task.md` / `docs/todo.md`：定義 owner、DoD、交接點

## 5. 架構影響面

### 5.1 模組影響矩陣

| 檔案 / 模組 | 現況 | 規劃變更 |
|---|---|---|
| `src/logsensing/config.py` | 已有 AAAK enable、entity map、summary item 上限、compact experience 偏好，以及 vector backend / bits / seed 設定 | 後續可再加入 benchmark / quality-gate 專用設定 |
| `src/logsensing/parser/drain.py` | 產出 `ParsedLine` / `LogTemplate` | 保持原介面；AAAK 目前作為後處理 hook，不直接污染核心 parser |
| `src/logsensing/parser/demux.py` | 提供 channel / module 邏輯 | 可重用於 AAAK entity map 來源 |
| `src/logsensing/rag/memory.py` | 已寫 JSON + Markdown experience，且可額外寫 `.aaak` compact 檔 | 後續可再擴充更多 compact schema / versioning |
| `src/logsensing/rag/chunker.py` | 文本與 log line 切塊 | 已可透過 compact experience 路徑進入既有 chunking pipeline |
| `src/logsensing/rag/vector.py` | float32 FAISS index | 作為 TurboQuant 不可用時的 fallback backend |
| `src/logsensing/rag/turboquant.py` | paper-derived 旋轉 + 低 bit quantization 壓縮索引 | 持續補 benchmark、quality gate、更多 metadata versioning |
| `src/logsensing/rag/retriever.py` | 依 search provider 做 RRF | 介面不應大改，保持 wiring 穩定 |
| `src/logsensing/cli.py` | 建 index、載 index、RAG 注入 agent，且已支援 AAAK compact experience writeback、`templates.aaak` 匯出與 backend fallback | 以 config / loader 層持續擴充，不破壞既有命令 |

### 5.2 目標資料流

```text
Raw Log
  -> StreamSplitter
  -> DrainParser
  -> (已落地) AAAK summarizer
  -> Analyzer / Agent / ExperienceArtifact
  -> (已落地) compact experience text
  -> DocumentChunker
  -> BM25Index + Vector backend (faiss / turboquant)
  -> HybridRetriever
```

### 5.3 設計原則

1. **保留現行 raw path**
2. **壓縮能力以 feature flag 控制**
3. **壓縮 backend 必須可完全拔除**
4. **先文件、後測試、再進 source**

## 6. 目前設定項（已實作）

```toml
[parser]
aaak_enabled = false
aaak_entity_map = {}
aaak_max_summary_items = 5

[rag]
prefer_compact_experience = false
vector_backend = "faiss"           # faiss | turboquant
vector_compression_bits = 4
vector_rotation_seed = 0
```

設定原則：

- 新設定預設必須對應現況行為。
- 若使用者沒有打開新設定，系統行為應與當前 release 等價。

## 7. 驗收條件

| 類別 | 驗收條件 |
|---|---|
| 相容性 | 現有 CLI 與既有 docs 描述的既有功能不可被破壞 |
| AAAK 功能 | 在代表性 log template / experience bundle 上，能提供可量化的 token 降低，且 raw path 可回退 |
| TurboQuant 功能 | 在代表性 retrieval query 上，需達成可接受的 recall / top-k overlap 門檻後才可預設開啟 |
| 授權 | 不得出現直接引用 GPL repo code 的情況 |
| 文件 | README、spec、test、plan、task、todo 的名詞與邊界一致 |
| 驗證 | 需保留既有 `pytest` / `ruff` / `mypy` runner，新增測試不得脫離現有工具鏈 |

## 8. 非目標

下列項目不屬於本次規格目標：

- 以 AAAK 取代 raw log 儲存
- 以 TurboQuant 取代 BM25
- 將 GPL-3.0 repo 直接納入專案
- 為了壓縮能力而重寫現有 CLI 介面

## 9. 交叉文件關係

| 文件 | 角色 |
|---|---|
| `docs/spec.md` | 定義邊界、目標、驗收與授權限制 |
| `docs/test.md` | 把規格轉成 test matrix 與驗證命令 |
| `docs/plan.md` | 把規格與測試風險轉成 roadmap 與 lane 切分 |
| `docs/task.md` | 把 roadmap 轉成可驗證任務 |
| `docs/todo.md` | 把任務下鑽成可派工的細粒度執行項 |
