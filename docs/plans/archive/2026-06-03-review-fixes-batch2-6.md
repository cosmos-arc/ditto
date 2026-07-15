# PR#66 Review Fixes — Batch 2-6 审查修复计划

> 状态：执行中

## 修复任务清单

### Critical（必须修复）

| # | 任务 | 文件 | 类型 |
|---|------|------|------|
| C1 | 提交工作区 `json → orjson` 修复 | post_ingest.py, catalog/sqlite_store.py, lineage/sqlite_store.py | 规约 |
| C2 | 修复 `_refresh_final_checkpoint` 逻辑 bug | backtest/engine.py | Bug |
| C3 | 提取 `_partition_keys_json` 到共享模块 | data/storage/base/sqlite_helpers.py, catalog/sqlite_store.py, lineage/sqlite_store.py | DRY |

### Important（建议修复）

| # | 任务 | 文件 | 类型 |
|---|------|------|------|
| I4 | 统一 `MetricDefinition` 到 kernel 或 platform | 7 个 observability/metrics.py | DRY |
| I5 | 治理 `SqliteOrderEventJournal`：close() 幂等 + 线程安全文档 | execution/orders/sqlite_journal.py | 质量 |
| I7 | 添加显式 `closed="left"` 到滚动操作符 | features/expression/codegen/_builders.py, _ts_operators.py | PIT |
| I8 | 更新路线图状态：待执行 → 已完成 | docs/plans/...roadmap.md | 文档 |
| I9 | 补充 CHANGELOG 重大功能条目 | CHANGELOG.md | 文档 |
| I10 | 更新 Batch 6 状态：实施中 → 已完成 | docs/plans/...batch6-ai-ready-design.md | 文档 |
| I11 | 移除 `_build_step_context` 多余 `get_slice()` 调用 | backtest/engine.py | 性能 |
| I12 | 修复 `BrokerEventRecordingGateway` frozen+mutable 矛盾 | execution/broker/recording.py | 设计 |

## 执行策略

- **并行组 A**（独立文件）: C1(已修), I5, I7, I12
- **并行组 B**（需要协调）: C3, I4, I11
- **串行组 C**（文档）: I8, I9, I10
- **最终**: C2(engine.py 需要先理解上下文)

## 验证

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
```
