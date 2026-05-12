# LogSensing AAAK / TurboQuant 研發 Roadmap

> 本文件描述「如何把 `docs/spec.md` 落地成可平行執行的研發與驗證流程」。不描述已完成 code 細節時，應回到 `docs/spec.md` 與 `docs/task.md` 查看。

## 0. 目前狀態

- P0 已完成：文件鏈與 README 索引已對齊。
- P1 已完成：AAAK contract、template/finding summary、`parse` 的 `templates.aaak` 匯出已落地。
- P2 已完成：experience `.aaak` writeback、`prefer_compact_experience` 與 RAG wiring 已落地。
- P3 進行中：paper-derived `TurboQuantVectorIndex`、metadata、save/load、HybridRetriever wiring 與 fallback 已有 prototype，但 benchmark / quality gate 尚未完成。

## 1. Roadmap 目標

本 roadmap 的核心目標是：

1. 以文件先行，鎖定 AAAK / TurboQuant 的技術邊界
2. 讓後續 `/fleet` 可以依 lane 平行實作
3. 讓 `/agent`、`/review`、`conventional-commit` 的交接點可直接從文件執行

## 2. 前置條件

- 整合分支：`feat/aaak-turboquant-foundation`
- 既有 docs 採 **增量修訂**，但需修正所有已與 code behavior 脫節的描述
- TurboQuant 僅採 paper-derived implementation；GPL repo 只用於理解，不進 source tree

## 3. Phase 規劃

| Phase | 目標 | 主要輸出 | 進入條件 | 退出條件 |
|---|---|---|---|---|
| P0 文件基線 | 完成 spec/test/plan/task/todo 文件鏈 | `docs/spec.md` `docs/test.md` `docs/plan.md` `docs/task.md` `docs/todo.md` | 研究結論已固定 | 文件鏈命名一致、README 已連結 |
| P1 AAAK parser core | 落地 parser / template / experience 的 compact summary 能力 | `parser/aaak.py`、config、unit tests | P0 完成 | raw path 保留、AAAK 關閉時行為等同現況 |
| P2 AAAK experience / RAG wiring | 將 compact summary 接進 experience writeback 與 chunking | memory / chunker / CLI wiring | P1 完成 | writeback 與 platform isolation 測試通過 |
| P3 TurboQuant backend | 以論文核心技術重作向量壓縮 backend | quantization module、backend metadata、驗證基線 | P0 完成；P1/P2 可並行後接 | 可回退到 float32 / BM25-only，且 quality gate 明確 |
| P4 驗證與收斂 | 完成整體驗證、review、commit、merge 收斂 | 測試報告、review report、commit history | P1~P3 完成 | 測試通過、review blocker 清空、文件與 code 對齊 |

## 4. Fleet lane 切分

> `/fleet` 應依「source ownership + validation ownership」切 lane，不建議只用單一文件或單一檔案拆分。

| Lane | 建議分支 | 範圍 | 主要輸出 |
|---|---|---|---|
| Parser / AAAK | `fleet/parser-aaak` | parser summary、entity map、config、parser tests | AAAK core + parser regression tests |
| Experience / RAG wiring | `fleet/experience-rag-wiring` | memory / chunker / retriever wiring | compact summary writeback + retrieval wiring |
| TurboQuant core | `fleet/rag-turboquant-core` | paper-derived quantization backend、vector metadata、load/save | 壓縮後端與 fallback path |
| Validation / Benchmark | `fleet/validation-bench` | golden queries、benchmark harness、test evidence | 品質與資源使用報告 |
| CLI / Docs / Integration | `fleet/cli-docs-integration` | CLI wiring、README、docs cross-check、release notes | 使用方式與文件一致性 |

## 5. Lane 依賴規則

1. `Parser / AAAK` 與 `TurboQuant core` 可在 P0 後平行推進。
2. `Experience / RAG wiring` 依賴 AAAK summary contract 穩定。
3. `Validation / Benchmark` 必須在各 lane 有可執行 prototype 後開始收斂。
4. `CLI / Docs / Integration` 應持續跟進，但最後 merge 前必須完成一次全量對齊。

## 6. `/agent`、`/review`、commit workflow

### 6.1 `/agent`

- 依 `docs/test.md` 執行指定測試層：
  - unit
  - functional
  - integration
  - boundary / stress
- 產出：
  - 執行命令
  - 成功 / 失敗案例
  - 與基線差異

### 6.2 `/review`

- 針對每條 lane 的 source diff 做 review
- 輸出：
  - blocker
  - non-blocker
  - 風險與建議回補測試
- review blocker 未清空前，不進入 commit / push

### 6.3 `/agent` + `conventional-commit`

- 在測試通過、review blocker 清空後，依實際 diff 產生 commit message
- commit message 必須對應 lane 與 change scope
- push 前需再次確認目標 branch 與文件版本同步

## 7. Merge Gate

每個 lane merge 前至少要滿足：

1. 對應 `docs/task.md` 任務完成
2. 對應 `docs/todo.md` 細項完成
3. `docs/test.md` 指定的必要測試有結果
4. `/review` blocker 已清空
5. README / spec / test / plan / task / todo 沒有明顯 drift

## 8. 風險與 rollback

| 風險 | 影響 | 對策 |
|---|---|---|
| AAAK 摘要品質不足 | LLM / RAG 可讀性下降 | 預設關閉；保留 raw path；先做 quality gate |
| TurboQuant 品質不穩 | retrieval 退化 | 先 paper-derived prototype；保留 float32 backend；以 benchmark gate 決定是否啟用 |
| lane 邊界重疊過多 | merge 衝突 | 先在 `docs/task.md` / `docs/todo.md` 固定 owner 與輸出 |
| 文件晚於程式更新 | doc drift | README 與 docs 視為 merge gate 一部分 |
| 授權邊界不清 | 法務風險 | 每份文件都要重申 paper-only / no GPL code import |

## 9. P0 完成定義

P0 被視為完成，需同時滿足：

- `docs/spec.md` 明確區分現況與規劃新增
- `docs/test.md` 已有 test matrix 與驗證命令
- `docs/plan.md` 已定義 phase 與 fleet lane
- `docs/task.md` 已定義任務、owner、DoD
- `docs/todo.md` 已細化到可直接派工
- README 已能導到完整文件集
