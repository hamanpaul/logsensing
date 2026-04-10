# LogSensing AAAK / TurboQuant 任務拆解

> 本文件以 `docs/plan.md` 為上位來源，將 roadmap phase 拆成可驗證任務。每個任務都必須能映射到明確輸出、owner 與完成定義。
> 目前狀態：P1-AAAK-01 ~ P2-EXP-03 已完成；P3-TQ-01 / P3-TQ-02 已完成第一版 prototype；P3-TQ-03 之後仍待驗證與收斂。

## 任務總表

| ID | Phase | 任務 | 輸入 | 輸出 | 依賴 | Owner | 完成定義（DoD） |
|---|---|---|---|---|---|---|---|
| P0-DOC-01 | P0 | 整理研究與現況基線 | research、README、現有 docs、核心 code | 新版 `docs/spec.md` 草稿 | 無 | integration | 清楚區分現況 / 規劃新增 / 授權邊界 |
| P0-DOC-02 | P0 | 建立測試矩陣 | `docs/spec.md`、既有 tests | `docs/test.md` | P0-DOC-01 | agent + integration | 有 risk matrix、backlog、驗證命令 |
| P0-DOC-03 | P0 | 建立 roadmap 與 lane 切分 | `docs/spec.md`、`docs/test.md` | 新版 `docs/plan.md` | P0-DOC-01、P0-DOC-02 | integration | phase、lane、merge gate 明確 |
| P0-DOC-04 | P0 | 建立 phase 任務表 | `docs/plan.md` | `docs/task.md` | P0-DOC-03 | integration | 每個任務都有輸出、依賴、DoD |
| P0-DOC-05 | P0 | 建立細粒度 todo | `docs/task.md` | 新版 `docs/todo.md` | P0-DOC-04 | integration | todo 可直接派工與驗證 |
| P0-DOC-06 | P0 | 修正 README 文件索引 | 文件集 | README docs section | P0-DOC-05 | integration | README 能導向完整文件集 |
| P1-AAAK-01 | P1 | 設計 AAAK data contract | `docs/spec.md` | `parser/aaak.py` 介面、config contract | P0-DOC-03 | fleet/parser-aaak | input/output、欄位命名、fallback 清楚 |
| P1-AAAK-02 | P1 | 實作 template / finding summary | AAAK contract | summary formatter、entity map 邏輯 | P1-AAAK-01 | fleet/parser-aaak | unit tests 通過，關閉 feature flag 時無行為漂移 |
| P1-AAAK-03 | P1 | 建立 AAAK parser 測試 | `docs/test.md`、summary formatter | parser / formatter tests | P1-AAAK-02 | agent | 對應 T01~T04 至少有 deterministic coverage |
| P2-EXP-01 | P2 | 將 compact summary 接進 experience writeback | AAAK contract、memory current behavior | memory compact path | P1-AAAK-02 | fleet/experience-rag-wiring | raw markdown 保留，compact path 可獨立驗證 |
| P2-EXP-02 | P2 | 將 compact summary 接進 chunker / retriever | P2-EXP-01 | chunking / retrieval wiring | P2-EXP-01 | fleet/experience-rag-wiring | platform isolation 與 retrieval path 維持正確 |
| P2-EXP-03 | P2 | 建立 experience / RAG integration 測試 | `docs/test.md`、RAG harness | integration tests、CLI smoke tests | P2-EXP-02 | agent | 對應 T04、T08、T09 通過 |
| P3-TQ-01 | P3 | 定義 paper-derived quantization contract | `docs/spec.md`、research | quantization interface、metadata schema | P0-DOC-03 | fleet/rag-turboquant-core | 清楚標記 no GPL code import |
| P3-TQ-02 | P3 | 實作壓縮向量 backend | quantization contract | backend prototype、save/load | P3-TQ-01 | fleet/rag-turboquant-core | 與 `VectorIndex` contract 對齊、可 fallback |
| P3-TQ-03 | P3 | 建立 golden query / benchmark harness | `docs/test.md`、existing RAG tests | benchmark scripts / tests | P3-TQ-02 | fleet/validation-bench | 有 quality gate 與 baseline 對照 |
| P3-TQ-04 | P3 | 完成 TurboQuant 驗證 | 壓縮 backend、golden queries | quality report | P3-TQ-03 | agent + review | 產出 recall / top-k overlap / resource comparison |
| P4-REL-01 | P4 | 整合 CLI / config / docs | P1~P3 輸出 | CLI wiring、README、docs 對齊 | P2-EXP-03、P3-TQ-04 | fleet/cli-docs-integration | 使用方式與設定說明一致 |
| P4-REL-02 | P4 | 執行 review 與 blocker 清理 | 完整 diff、測試結果 | review report、fix list | P4-REL-01 | review | blocker 清空或有明確 not-fix 理由 |
| P4-REL-03 | P4 | 產生 commit / push 產物 | 測試通過 + review clean | conventional commit、push 紀錄 | P4-REL-02 | agent | commit message 對應 diff，push 到正確 branch |
| P4-REL-04 | P4 | 收斂 anomaly 報表輸出 | b-log regression evidence、現有 analyze JSON | dedup / grouping 邏輯、較穩定的問題清單輸出 | P2-EXP-03 | fleet/cli-docs-integration | 高頻重複 signature 不再只以逐行命中呈現 |

## 任務依賴摘要

```text
P0-DOC-01
  -> P0-DOC-02
  -> P0-DOC-03
      -> P0-DOC-04
          -> P0-DOC-05
              -> P0-DOC-06

P0 完成
  -> P1-AAAK-01 -> P1-AAAK-02 -> P1-AAAK-03
  -> P3-TQ-01 -> P3-TQ-02 -> P3-TQ-03 -> P3-TQ-04

P1-AAAK-02
  -> P2-EXP-01 -> P2-EXP-02 -> P2-EXP-03

P2-EXP-03 + P3-TQ-04
  -> P4-REL-01 -> P4-REL-02 -> P4-REL-03
```

## Owner 類型說明

| Owner | 職責 |
|---|---|
| `integration` | 維護整體規格與文件鏈一致性 |
| `fleet/parser-aaak` | AAAK parser / summary 相關 code 與單元測試 |
| `fleet/experience-rag-wiring` | experience writeback、chunker、retriever wiring |
| `fleet/rag-turboquant-core` | paper-derived quantization backend |
| `fleet/validation-bench` | golden queries、benchmark、quality report |
| `fleet/cli-docs-integration` | CLI 設定對齊、README、整體文件一致性 |
| `agent` | 執行測試、回報結果、必要時協助產生驗證工件 |
| `review` | code / diff review、blocker 收斂 |
