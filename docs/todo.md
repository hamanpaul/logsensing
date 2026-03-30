# LogSensing 開發待辦追蹤

> 狀態定義：⬜ 待辦 | 🔧 進行中 | ✅ 完成 | 🚫 阻塞

---

## Sprint 0：專案骨架

| ID | 任務 | 狀態 | 備註 |
|----|------|------|------|
| S0-01 | 初始化 pyproject.toml（uv） | ✅ | Python 3.10+, src layout |
| S0-02 | 建立 src/logsensing/ 目錄結構 | ✅ | 含 parser/, analyzer/, agent/, rag/ |
| S0-03 | 設定 ruff + mypy 組態 | ✅ | pyproject.toml 內嵌 |
| S0-04 | 設定 pytest + conftest.py | ✅ | |
| S0-05 | 建立 samples/ 目錄與測試用日誌樣本 | ✅ | 已有 docs/sample_logs/ 實際日誌 |
| S0-06 | 撰寫 README.md 第一版 | ✅ | |

---

## Sprint 1：Parser & Normalizer

| ID | 任務 | 狀態 | 依賴 | 備註 |
|----|------|------|------|------|
| S1-01 | 實作 StreamSplitter 核心邏輯 | ✅ | S0-02 | 串流式切割，記憶體保護 |
| S1-02 | 實作錨點設定載入（多錨點 + regex） | ✅ | S1-01 | config.toml 整合 |
| S1-03 | 整合 Drain3，實作 DrainParser | ✅ | S0-02 | 模板探勘 + 參數萃取 |
| S1-04 | 實作 Drain3 模型持久化（save/load） | ✅ | S1-03 | |
| S1-05 | 實作 Demultiplexer | ✅ | S1-03 | PID / 模組前綴分流 |
| S1-06 | 實作時間戳記解析器 | ✅ | S1-01 | 多格式時間戳自動偵測 |
| S1-07 | 撰寫 StreamSplitter 單元測試 | ✅ | S1-01 | 17 tests |
| S1-08 | 撰寫 DrainParser 單元測試 | ✅ | S1-03 | 18 tests |
| S1-09 | 撰寫 Demultiplexer 單元測試 | ✅ | S1-05 | 29 tests |
| S1-10 | Sprint 1 整合測試 | ✅ | S1-01~S1-09 | 端到端 parse pipeline |

---

## Sprint 2：Rule Engine & Analyzer

| ID | 任務 | 狀態 | 依賴 | 備註 |
|----|------|------|------|------|
| S2-01 | 定義 Milestone 資料模型 | ✅ | S1-03 | dataclass model |
| S2-02 | 實作 BaselineProfiler（train） | ✅ | S2-01 | 從正常 cycle 訓練 |
| S2-03 | 實作 BaselineProfiler（save/load） | ✅ | S2-02 | |
| S2-04 | 定義 AnomalyRule 規則模型 | ✅ | | pattern / timeout / sequence |
| S2-05 | 實作 AnomalyDetector 核心 | ✅ | S2-02, S2-04 | |
| S2-06 | 實作 pattern 規則偵測 | ✅ | S2-05 | Kernel panic, OOM 等 |
| S2-07 | 實作 timeout 規則偵測 | ✅ | S2-05 | 基於 baseline σ 判定 |
| S2-08 | 實作 sequence 規則偵測 | ✅ | S2-05 | 缺失里程碑偵測 |
| S2-09 | 實作 ContextClipper | ✅ | | 前後 N 行裁切 |
| S2-10 | 實作 OTel Exporter | ✅ | S2-05 | anomalies.json 輸出 |
| S2-11 | 撰寫 Analyzer 模組單元測試 | ✅ | S2-05~S2-10 | 21 tests |
| S2-12 | Sprint 2 整合測試 | ✅ | S2-all | parse → analyze 管線 |

---

## Sprint 3：CLI 封裝與 Agent 整合

| ID | 任務 | 狀態 | 依賴 | 備註 |
|----|------|------|------|------|
| S3-01 | 實作 Typer CLI 入口 | ✅ | S1, S2 | parse / analyze / agent / train |
| S3-02 | 實作 `parse` 子命令 | ✅ | S3-01 | |
| S3-03 | 實作 `analyze` 子命令 | ✅ | S3-01 | |
| S3-04 | 實作 `train baseline` 子命令 | ✅ | S3-01 | |
| S3-05 | 實作 `train drain` 子命令 | ✅ | S3-01 | |
| S3-06 | 實作組態管理（config.toml） | ✅ | | toml 載入 + pydantic 驗證 |
| S3-07 | 定義 LLM Function Calling 工具 | ✅ | S2-10 | 6 個 tools（含 search_knowledge_base） |
| S3-08 | 實作 RCA Agent 自動分析 | ✅ | S3-07 | LLM RCA + 規則式 fallback |
| S3-09 | 實作 `agent analyze` 子命令 | ✅ | S3-08 | |
| S3-10 | 實作 Interactive Q&A | ✅ | S3-07 | Rich TUI + LLM 對話 |
| S3-11 | 實作 `agent chat` 子命令 | ✅ | S3-10 | |
| S3-12 | 撰寫 CLI 測試 | ✅ | S3-01~S3-11 | 9 tests |
| S3-13 | Sprint 3 端到端測試 | ✅ | S3-all | 完整管線驗證 |

---

## Sprint 4：混合 RAG 知識庫

| ID | 任務 | 狀態 | 依賴 | 備註 |
|----|------|------|------|------|
| S4-01 | 實作文件切塊器 | ✅ | | Markdown / 純文字 / 日誌行 → chunks |
| S4-02 | 實作 BM25 索引建置與查詢 | ✅ | S4-01 | rank-bm25, save/load 支援 |
| S4-03 | 實作 FAISS 向量索引 | ✅ | S4-01 | sentence-transformers + faiss-cpu |
| S4-04 | 實作混合檢索 API（融合排序） | ✅ | S4-02, S4-03 | RRF (Reciprocal Rank Fusion) |
| S4-05 | Agent 知識庫整合 | ✅ | S4-04, S3-08 | search_knowledge_base tool |
| S4-06 | 撰寫 RAG 模組測試 | ✅ | S4-all | 30 tests (19 RAG + 11 tools) |

---

## 持續性任務

| ID | 任務 | 狀態 | 備註 |
|----|------|------|------|
| C-01 | 維護測試覆蓋率 ≥ 80% | ✅ | 143 tests, 132 passed, 11 skipped（缺 sample log） |
| C-02 | 更新文件（spec.md / README.md） | ✅ | 隨開發進度更新 |
| C-03 | 收集實際裝置日誌樣本 | ✅ | 已有 `docs/sample_logs/20260318_ATT_newHW7-normal_1354.log`（7MB, 113K 行, 25 cycles, BGW720-300） |
