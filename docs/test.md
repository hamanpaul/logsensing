# LogSensing AAAK / TurboQuant 測試計畫

> 依據：`docs/spec.md`、研究文件 `ref-https-github-com-milla-jovovich-mempalace-inte.md`，以及現有 `pytest` 測試與 CLI / RAG / parser harness。

## 1. 專案摘要

- **系統型態**：CLI + library，含 parser、analyzer、agent、RAG
- **build / test 指令**：
  - `uv run pytest`
  - `uv run ruff check .`
  - `uv run mypy src/`
- **主要 actor**：
  - 使用者 / 開發者
  - `logsensing` CLI
  - parser / analyzer / RAG 元件
  - optional LLM client
  - filesystem-based platform RAG store
- **外部依賴**：
  - `drain3`
  - `jsonpickle`
  - optional `faiss-cpu`
  - optional `sentence-transformers`
  - optional `openai`
- **持久化**：
  - Drain state
  - baseline / anomalies JSON
  - BM25 / FAISS index
  - platform experience JSON / Markdown
- **狀態機**：
  - parse -> analyze -> agent -> writeback -> reload
  - RAG backend：none / BM25-only / BM25+vector
  - platform store isolation：`<index_root>/<platform>/...`
- **非同步邊界**：
  - 目前核心邏輯多為同步 CLI flow
  - 外部模型 encode / LLM API / index rebuild 屬於慢邊界
  - 本次測試重點仍以 deterministic unit / integration 為主

## 2. ProblemMap Intake（依研究與現況抽取）

| Node | 症狀 | 假設層 | 可觀測訊號 | 排查方式 | recover 手段 | 建議測試化方式 |
|---|---|---|---|---|---|---|
| P01 | AAAK 摘要缺少 severity / cycle / rule 資訊 | parser / summary contract | compact summary 欄位缺漏 | 對照 raw template 與 artifact | 關閉 AAAK、回退 raw path | regression |
| P02 | entity code 與 module / channel 對不上 | entity mapping | module code 不穩定 | 比對 demux channel 與 summary 輸出 | 修正 mapping / fallback raw | unit |
| P03 | compact experience 破壞 writeback / retrieval | memory / chunker / metadata | experience 缺欄位、檢索不到 | 檢查 markdown / json / metadata | 回退 raw markdown | integration |
| P04 | TurboQuant 壓縮後檢索品質下降過多 | vector backend | top-k overlap / recall 降低 | 對照 float32 baseline | 切回 float32 backend | benchmark / regression |
| P05 | 壓縮 metadata save/load 不相容 | persistence | load 失敗、結果異常 | round-trip 檢查 + metadata diff | 重建索引 / fallback | component |
| P06 | optional 依賴缺失時路徑錯誤 | fallback | import error / empty result | 模擬依賴缺失 | BM25-only / raw path | functional |
| P07 | platform store 被交叉污染 | platform isolation | query 命中錯平台資料 | 多平台 fixture 驗證 | 重新建 store | integration |
| P08 | 文件與 code 行為不一致 | usage drift | README / docs 說法錯誤 | doc audit | 更新文件 | documentation assertion |

## 3. 既有 harness 優先重用

| Harness / Fixture | 來源 | 可重用用途 |
|---|---|---|
| `DrainParser` fixture、sample log、line-level assertions | `tests/test_drain.py` | AAAK 前置 parser 行為、template convergence、module extraction |
| `_make_chunks()`、`sample_chunks`、`FakeEncoder` | `tests/test_rag.py` | vector backend contract、retriever 行為、save/load 基線 |
| `build_experience_artifact()`、platform store fixtures | `tests/test_rag_memory.py` | experience writeback、platform isolation、retriever reload |
| `CliRunner`、fake LLM / monkeypatch | `tests/test_cli.py` | CLI wiring、config 路徑、agent/RAG 整合 smoke test |
| `tmp_path`、`pytest.importorskip`、`slow` marker | 既有 pytest 慣例 | 隔離持久化、optional 依賴、重型測試分層 |

## 3.1 已落地測試基線

- [x] AAAK config 預設值測試
- [x] AAAK template / finding / RCA compact summary formatter 測試
- [x] experience compact summary 建立與 `.aaak` 寫檔測試
- [x] `prefer_compact_experience` 的 RAG 讀取偏好測試
- [x] `agent analyze` 啟用 AAAK 後的 compact writeback 測試
- [x] `parse` 啟用 AAAK 後輸出 `templates.aaak` 測試
- [x] TurboQuant-style backend 的 `build/search/save/load` contract 測試
- [x] TurboQuant metadata round-trip 與 HybridRetriever 整合測試
- [x] prplOS external `~/b-log/...` anomaly regression 與 CLI smoke test

## 4. 風險矩陣

| ID | Surface | 風險 | 觸發條件 | Observable | Oracle | 測試層 | Harness | 優先級 |
|---|---|---|---|---|---|---|---|---|
| T01 | AAAK entity map | module 對應錯誤 | 新 module / channel 進入 summary | summary code 不合理 | code 與 demux 規則一致 | Unit | `tests/test_drain.py` + demux fixtures | P0 |
| T02 | AAAK summary contract | 欄位遺失或格式漂移 | template / finding 壓縮 | compact text 結構不穩定 | 固定欄位齊全、可被 parser/LLM 使用 | Unit | 新 summary formatter tests | P0 |
| T03 | Parser fallback | 關閉 AAAK 時行為改變 | feature flag off | parse / analyze 結果不同 | off 時輸出等同現況 | Functional | existing CLI + parser tests | P0 |
| T04 | Experience writeback | compact path 破壞 JSON/MD | write_experience_artifact | 檔案缺失、重複寫入異常 | json / md / compact 皆可驗證 | Integration | `tests/test_rag_memory.py` | P0 |
| T05 | Vector backend contract | 壓縮 backend 不相容 `search/save/load` | 替換 backend | retriever 無法查詢 | contract 與 float32 backend 對齊 | Component | `tests/test_rag.py` | P0 |
| T06 | Retrieval quality | TurboQuant recall 下降 | 壓縮 bits 過低 / rotation 錯誤 | golden query 命中下降 | 與 float32 baseline 差異在門檻內 | Benchmark | new golden-query harness | P1 |
| T07 | Persistence metadata | backend metadata round-trip 錯誤 | save/load | 無法載入或結果飄移 | metadata 完整且版本相容 | Component | `tmp_path` round-trip | P1 |
| T08 | Platform isolation | 資料跨平台污染 | 多平台資料同時存在 | 查到錯平台 chunk | hit 的 platform metadata 正確 | Integration | `tests/test_rag_memory.py` | P0 |
| T09 | Fallback / deps missing | optional 依賴缺失時錯誤 | 缺 `faiss` / `sentence-transformers` | import error / crash | 自動退回 BM25-only | Functional | importorskip / monkeypatch | P0 |
| T10 | Usage drift | docs 與 code 不一致 | 實作後未回寫文件 | README / docs 說法不符 | 文件與 runner / CLI 一致 | Functional | doc audit + CLI help tests | P0 |

## 5. Test Backlog

### Phase 1：deterministic

- [x] AAAK entity map：module -> entity code 規則測試
- [x] AAAK summary formatter：template / finding / evidence 欄位完整性測試
- [x] config parsing：新增 parser / rag 壓縮設定的預設值測試
- [x] vector backend contract：`build/search/save/load` 介面對齊測試
- [x] metadata schema：壓縮 index metadata round-trip 測試

### Phase 2：recovery / fallback

- [ ] `aaak_enabled = false` 時 raw path 行為不變
- [ ] summary 產生失敗時回退 raw markdown / raw context
- [x] 壓縮 backend 不可用時回退 float32 `VectorIndex`
- [ ] 向量依賴缺失時仍維持 BM25-only
- [ ] metadata 不相容時拒絕載入並要求重建

### Phase 3：integration / isolation

- [x] compact experience 與現有 experience writeback 共存
- [x] platform-scoped RAG store 仍維持隔離
- [x] retriever 可同時處理 BM25 與壓縮向量 backend
- [x] CLI / config / RAG loader wiring smoke test

### Phase 4：boundary / benchmark

- [ ] 代表性 template / experience bundle 的 token reduction 量測
- [ ] float32 vs compressed backend 的 top-k overlap / recall 比較
- [ ] 大量 chunk / 大量 template / 長 experience 文件的記憶體與時間量測
- [ ] turbo2 / turbo3 / turbo4 的品質與資源比較

### Phase 5：functional / docs

- [ ] README / docs / config 範例與實際 runner 對齊檢查
- [ ] CLI help 與文件中新增設定對齊
- [ ] `/agent` 測試回報格式與 review gate 文件化

## 6. 驗證命令

```bash
# parser / AAAK 前置基線
uv run pytest tests/test_drain.py

# RAG / experience / retriever
uv run pytest tests/test_rag.py tests/test_rag_memory.py

# CLI / wiring / help
uv run pytest tests/test_cli.py

# 全套既有測試
uv run pytest

# 靜態檢查
uv run ruff check .
uv run mypy src/logsensing/cli.py src/logsensing/rag/turboquant.py
```

補充說明：

- `VectorIndex` 相關測試依賴 `faiss` / `sentence-transformers`，既有測試已使用 `pytest.importorskip`。
- `TurboQuantVectorIndex` contract tests 使用 `FakeEncoder`，不需要額外模型相依即可驗證 metadata 與 search contract。
- `tests/test_rag.py` 中 vector 測試已有 `slow` marker，可用於分層執行。
- 若 sample log 不存在，部分 functional 測試會 skip；這應視為環境條件，而非測試失敗。

## 7. `/agent` 執行與回報格式

`/agent` 執行測試時，回報至少應包含：

1. 使用的命令
2. 目標測試層（unit / functional / integration / boundary）
3. 成功 / 失敗案例摘要
4. 若失敗，指出對應 `docs/task.md` / `docs/todo.md` 任務
5. 是否阻塞 merge

## 8. 文件對齊檢查

- [ ] README 是否加入 `docs/test.md`、`docs/task.md`
- [ ] `docs/spec.md` 是否清楚區分現況與規劃新增
- [ ] `docs/plan.md` 的 lane 與 `docs/task.md` owner 是否一致
- [ ] `docs/todo.md` 的細項是否可追溯回 `docs/task.md`
