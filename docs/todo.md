# LogSensing AAAK / TurboQuant 細粒度 Todo

> 狀態欄預設使用：`⬜` 待做 / `🔧` 進行中 / `✅` 完成 / `🚫` 阻塞。
> 本文件每一列都必須可追溯回 `docs/task.md` 的任務 ID。

| Todo ID | 對應任務 | 細項 | 驗證方式 | Owner | 狀態 | 備註 |
|---|---|---|---|---|---|---|
| TD-001 | P0-DOC-01 | 從 research 文件抽出 AAAK / TurboQuant 邊界與授權限制 | `docs/spec.md` 有獨立授權邊界段落 | integration | ✅ | 已明講 paper-only / no GPL import |
| TD-002 | P0-DOC-01 | 對齊現有 parser / rag / memory / config code 行為 | `docs/spec.md` 現況表與 source 對齊 | integration | ✅ | 已持續回寫，避免把未實作內容寫成現況 |
| TD-003 | P0-DOC-02 | 盤點既有測試 harness 與 runner | `docs/test.md` 有 reuse harness 表 | integration | ✅ | 已重用 `pytest` 既有結構 |
| TD-004 | P0-DOC-02 | 建立 AAAK 風險矩陣 | `docs/test.md` 包含 T01~T04 | integration | ✅ | 已涵蓋 entity map / summary / fallback |
| TD-005 | P0-DOC-02 | 建立 TurboQuant 風險矩陣 | `docs/test.md` 包含 T05~T10 | integration | ✅ | 已涵蓋 contract / recall / metadata / docs drift |
| TD-006 | P0-DOC-03 | 在 roadmap 定義 phase 與退出條件 | `docs/plan.md` phase 表完整 | integration | ✅ | 已以 gate 表述，不寫工期 |
| TD-007 | P0-DOC-03 | 在 roadmap 定義 fleet lanes | `docs/plan.md` lane 表完整 | integration | ✅ | lane 名稱與 branch 前綴已對齊 |
| TD-008 | P0-DOC-03 | 明確定義 `/agent`、`/review`、commit workflow | `docs/plan.md` 有專章 | integration | ✅ | 已對齊 user 指定邊界 |
| TD-009 | P0-DOC-04 | 為每個 phase 任務補 owner | `docs/task.md` owner 欄完整 | integration | ✅ | 已含 fleet / agent / review |
| TD-010 | P0-DOC-04 | 為每個任務補完成定義 | `docs/task.md` DoD 欄完整 | integration | ✅ | DoD 已可驗證 |
| TD-011 | P0-DOC-05 | 把文件任務拆成可直接派工的 todo | `docs/todo.md` 可追溯到 task ID | integration | ✅ | todo 粒度已小於 task |
| TD-012 | P0-DOC-06 | 更新 README 文件索引 | README 文件清單完整 | integration | ✅ | 已補 test/task 與設定說明 |
| TD-013 | P1-AAAK-01 | 定義 AAAK config key 與預設值 | spec / 後續 code contract 一致 | fleet/parser-aaak | ✅ | 已新增 `aaak_enabled`、`aaak_entity_map`、`aaak_max_summary_items` 與 compact preference |
| TD-014 | P1-AAAK-01 | 定義 compact summary 欄位命名 | summary formatter 測試可寫 | fleet/parser-aaak | ✅ | 已固定 `aaak-log-v1` 與 `EXP/F/TPL/RCA` line contract |
| TD-015 | P1-AAAK-02 | 建立 module -> entity code 規則 | unit test 通過 | fleet/parser-aaak | ✅ | 內建 wifi/dhd/rpc/pcie/kernel/offload/network 對應 |
| TD-016 | P1-AAAK-02 | 建立 template / finding 壓縮格式 | formatter 測試通過 | fleet/parser-aaak | ✅ | raw path 保留，compact summary 為增量產物 |
| TD-017 | P2-EXP-01 | 為 experience 新增 compact path | writeback 測試通過 | fleet/experience-rag-wiring | ✅ | 已新增 `.aaak` writeback，JSON/Markdown 仍保留 |
| TD-018 | P2-EXP-02 | 決定 compact summary 如何進入 chunker | integration test 通過 | fleet/experience-rag-wiring | ✅ | `prefer_compact_experience` 會優先讀 `.aaak`，否則回退 markdown |
| TD-019 | P2-EXP-03 | 擴充 platform isolation 測試 | `tests/test_rag_memory.py` 類型測試通過 | agent | ✅ | 已補 compact 與 platform isolation 測試 |
| TD-020 | P3-TQ-01 | 定義 quantization metadata schema | round-trip 測試可覆蓋 | fleet/rag-turboquant-core | ✅ | 已包含 backend / version / bits / dim / padded_dim 與 chunk metadata |
| TD-021 | P3-TQ-01 | 補授權聲明與實作邊界 | spec / plan / code comments 一致 | fleet/rag-turboquant-core | ✅ | 已明講 no GPL code import |
| TD-022 | P3-TQ-02 | 實作壓縮 backend `build/search/save/load` contract | component tests 通過 | fleet/rag-turboquant-core | ✅ | 已新增 `src/logsensing/rag/turboquant.py`，且不破壞 `HybridRetriever` wiring |
| TD-023 | P3-TQ-02 | 建立 float32 fallback path | fallback 測試通過 | fleet/rag-turboquant-core | ✅ | 已補 TurboQuant load fail -> FAISS fallback 與雙失敗不 crash 測試 |
| TD-024 | P3-TQ-03 | 建立 golden query corpus 與 baseline | benchmark 可重跑 | fleet/validation-bench | ⬜ | query 要覆蓋 kernel / wifi / rpc / boot |
| TD-025 | P3-TQ-04 | 產出 recall / top-k overlap / 資源比較報告 | review 可引用報告 | fleet/validation-bench | ⬜ | 決定 turbo4 是否可作預設 |
| TD-026 | P4-REL-01 | 對齊 CLI / config / README 使用方式 | CLI help / docs audit 通過 | fleet/cli-docs-integration | ✅ | 已同步 AAAK parser export 與 vector backend 設定 |
| TD-027 | P4-REL-02 | 依 `/review` 產出 blocker 清單與修復追蹤 | review report 存在 | review | ⬜ | false positive 需明記不修原因 |
| TD-028 | P4-REL-03 | 以 conventional commit 產生 commit message 並 push | commit / push 成功 | agent | ⬜ | 只在測試與 review 通過後執行 |
| TD-029 | P3-TQ-03 | 整理 `docs/sample_logs` 與 `~/b-log` fixture 來源 | skipped 測試可重現或以 config 掛載 | fleet/validation-bench | ⬜ | 降低目前 16 skipped，支援 benchmark / regression |
| TD-030 | P3-TQ-03 | 建立 b-log ground truth 與 golden query 集 | benchmark 命中集可重跑 | fleet/validation-bench | ⬜ | 至少覆蓋 boot / storage / wifi / fatal signal 類問題 |
| TD-031 | P4-REL-04 | 將 anomaly 結果做 dedup / grouping | b-log 報告可輸出較穩定問題清單 | fleet/cli-docs-integration | ⬜ | 降低 `cfg80211_error` 類高頻重複噪音 |

## 文件交叉檢查

- [ ] `docs/spec.md` 的名詞與設定鍵，有在 `docs/test.md` / `docs/plan.md` / `docs/task.md` / `docs/todo.md` 出現時保持一致
- [ ] lane 名稱在 `docs/plan.md` 與 `docs/task.md` 完全一致
- [ ] `docs/todo.md` 中每個 Todo 都能追到 `docs/task.md` 的任務 ID
- [ ] README 文件索引與實際 docs 檔名一致
