# 策略引擎 v3 — 审计修复收尾 + P1 待完善项

## 概述
- Sprint: post-audit | Phase: v3 收尾
- 创建: 2026-03-24
- 前置: v3 Phase 0-5 已完成（3959 测试通过），剩余任务 11 项 + 审计修复 7 项已关闭

## 背景

v3 设计文档的 37 项修订（R1-R12, F1-F6, S1-S5, B1-B4, P1-P5）全部落地。
当前工作树有 11 文件 988 行未提交改动，属于审计修复后续收尾工作。
本轮 Sprint 聚焦：**提交收尾 + 修复 P1 遗漏项**。

---

## Part 01: 提交当前未提交改动

> 当前 11 文件 988 行改动，经 review 确认均为审计修复后续工作，质量合格。

### 改动清单

| 文件 | 类型 | 行数 | 说明 |
|------|------|------|------|
| `packages/core/src/ditto_core/backtest/engine.py` | 源码 | +38 | TradeBuilder 接入 + audit 记录 + flush 未平仓交易 |
| `packages/data/src/ditto_data/models/strategy.py` | 源码 | +25 | `ArtifactKind` 枚举 + `StrategyArtifactRecord.artifact_type` 类型化 |
| `packages/data/src/ditto_data/models/__init__.py` | 源码 | +3 | 导出 `ArtifactKind` |
| `apps/port/src/ditto_port/services/strategy/backtest_service.py` | 源码 | ±4 | `artifact_type` 改用 `ArtifactKind` 枚举 |
| `apps/port/src/ditto_port/services/strategy/input_assembler.py` | 源码 | +9 | `valid_until` 信号过期检查 |
| `apps/port/src/ditto_port/services/strategy/strategy_run_service.py` | 源码 | +23 | `spec` 参数 + `validate_spec_params` 运行时校验 |
| `packages/core/tests/integration/backtest/test_backtest_invariants.py` | 测试 | +438 | Suspended E2E + ExitOrderRules + RuleRefsPreserved |
| `packages/core/tests/unit/backtest/test_statistics_helpers_unit.py` | 测试 | +174 | PortfolioStatistics 不变量测试 |
| `packages/core/tests/unit/execution/test_fill_model_unit.py` | 测试 | +142 | AShareFillModel 参数化场景矩阵 |
| `apps/port/tests/unit/services/strategy/test_input_assembler_unit.py` | 测试 | +56 | valid_until 过期检查测试 |
| `apps/port/tests/unit/services/strategy/test_strategy_run_service_unit.py` | 测试 | +90 | spec 参数校验测试 |

### 验收标准

- [ ] `pixi run -e dev check` 通过
- [ ] 分支覆盖率 >= 80%
- [ ] commit message 准确描述改动范围

### 建议 commit 策略

拆为 2 个 commit：
1. **feat: ArtifactKind 枚举 + 模型类型化** — strategy.py, __init__.py, backtest_service.py
2. **feat: EngineLoop 审计接入 + valid_until + validate_spec_params + 证明型测试** — 其余 8 文件

---

## Part 02: P1-1 StrategySpecRecord / StrategyArtifactRecord 导出补全

> **问题**: `StrategySpecRecord` 和 `StrategyArtifactRecord` 定义在 `models/strategy.py` 的 `__all__` 中，但 `models/__init__.py` 未导出。外部使用方需 `from models.strategy import` 而非 `from models import`。

- [ ] Task: 在 `models/__init__.py` 中导出 `StrategySpecRecord`, `StrategyArtifactRecord` `[S]`
  - 验收: `from ditto_data.models import StrategySpecRecord, StrategyArtifactRecord` 可用
  - 文件: `packages/data/src/ditto_data/models/__init__.py`
  - 测试: 无需新增测试（现有导入已覆盖）

---

## Part 03: P1-2 BacktestService artifact 序列化

> **问题**: `BacktestService.run()` 中 `file_path=""` 标注 `TODO: serialize report to file`。BacktestReport 产出后未持久化到 Parquet/JSON。

### 技术方案

- BacktestReport 的 JSON 序列化走 `orjson`（项目标准）
- nav_series / trade_log / fill_log 等 tabular 数据走 Parquet
- 序列化路径: `{artifact_dir}/strategy/runs/{strategy_id}/v{version}/{run_id}/`
- 文件名与 v3 §8.5 artifact 目录规范对齐

- [ ] Task: 实现 `BacktestReportSerializer` — 将 BacktestReport 序列化为 JSON + Parquet `[M]`
  - 验收: `serialize(report, output_dir)` 产出 `backtest_report.json` + `nav.parquet` + `trade_log.parquet` + `fill_log.parquet`
  - 文件:
    - `packages/core/src/ditto_core/backtest/serialization.py` (新建)
  - 测试:
    - `packages/core/tests/unit/backtest/test_serialization_unit.py` (新建)
    - 覆盖: 空 report / 有交易 report / 特殊字符 instrument_id

- [ ] Task: BacktestService 接入序列化，填 TODO `[S]`
  - 验收: `BacktestService.run()` 后 `file_path` 非空，指向实际文件
  - 文件: `apps/port/src/ditto_port/services/strategy/backtest_service.py`
  - 测试: 更新 `test_backtest_service_unit.py` 验证 file_path

---

## Part 04: P1-3 StrategyCatalogService 真实存储实现

> **问题**: `StrategyCatalogService` 和 `StrategyArtifactService` 使用 Protocol 模式，Reader/Writer 仅有 mock 实现，无真实持久化。

### 技术方案

- **存储选型**: SQLite（与 `ExecutionAuditService` 一致，项目已有 SQLitePool）
- **表设计**:
  - `strategy_spec`: `strategy_id TEXT, version INT, name TEXT, spec_json TEXT, status TEXT, tags TEXT, created_at TEXT, updated_at TEXT, PRIMARY KEY (strategy_id, version)`
  - `strategy_artifact`: `artifact_id TEXT PRIMARY KEY, strategy_id TEXT, run_id TEXT, artifact_type TEXT, file_path TEXT, metadata TEXT, status TEXT, created_at TEXT`
- **Reader/Writer 实现**: `SQLiteStrategySpecReader`, `SQLiteStrategySpecWriter`, `SQLiteStrategyArtifactReader`, `SQLiteStrategyArtifactWriter`

- [ ] Task: SQLite strategy_spec 表 + Reader/Writer 实现 `[M]`
  - 验收:
    - `save_spec` / `get_spec` / `list_specs` / `list_versions` / `publish_spec` 全链路
    - 重复 save 覆盖、不存在的 get 返回 None
  - 文件:
    - `packages/data/src/ditto_data/stores/metadata/strategy_spec_store.py` (新建)
    - `packages/data/tests/unit/stores/metadata/test_strategy_spec_store_unit.py` (新建)

- [ ] Task: SQLite strategy_artifact 表 + Reader/Writer 实现 `[M]`
  - 验收:
    - `save_artifact` / `get_artifact` / `list_artifacts` / `list_by_strategy` / `archive_artifact` 全链路
  - 文件:
    - `packages/data/src/ditto_data/stores/metadata/strategy_artifact_store.py` (新建)
    - `packages/data/tests/unit/stores/metadata/test_strategy_artifact_store_unit.py` (新建)

- [ ] Task: StrategyCatalogService + StrategyArtifactService 接入真实存储 `[S]`
  - 验收: 构造时传入 SQLite Reader/Writer，功能与 mock 测试一致
  - 文件: `packages/data/src/ditto_data/services/strategy/` (无改动，Protocol 已支持)
  - 测试: 更新现有 service 测试，用真实 SQLite 替代 mock

---

## Part 05: P1-4 TradingRule / FeeSchedule 真实存储升级

> **问题**: `TradingRuleReader/Writer` 和 `FeeScheduleReader/Writer` 为 V1 内存实现，数据硬编码在测试中，无法从外部加载。

### 技术方案

- **存储选型**: SQLite（同上）
- **表设计**:
  - `trading_rule`: `instrument_id TEXT, as_of_date TEXT, settlement_cycle INT, fund_settlement_cycle INT, price_limit_pct REAL, order_types_supported TEXT, call_auction_sessions TEXT, effective_from TEXT, effective_to TEXT, PRIMARY KEY (instrument_id, as_of_date)`
  - `fee_schedule`: `instrument_id TEXT, as_of_date TEXT, commission_rate REAL, min_commission REAL, stamp_duty_rate REAL, transfer_fee_rate REAL, effective_from TEXT, effective_to TEXT, PRIMARY KEY (instrument_id, as_of_date)`
- **PIT 查询**: 复用现有 `_pit_base.PITRecordReader/Writer` 的 SQLite 分支（如果已有），否则扩展

- [ ] Task: TradingRule SQLite 存储 + PIT 查询 `[M]`
  - 验收:
    - 写入 3 个版本规则 → 查询 as_of_date 返回正确版本
    - 边界: effective_to=None（永久有效）、重叠区间
  - 文件:
    - `packages/data/src/ditto_data/stores/metadata/trading_rule_store.py` (新建，替代 V1 内存)
    - `packages/data/tests/unit/stores/metadata/test_trading_rule_store_unit.py` (新建)

- [ ] Task: FeeSchedule SQLite 存储 + PIT 查询 `[M]`
  - 验收: 同 TradingRule
  - 文件:
    - `packages/data/src/ditto_data/stores/metadata/fee_schedule_store.py` (新建)
    - `packages/data/tests/unit/stores/metadata/test_fee_schedule_store_unit.py` (新建)

- [ ] Task: InstrumentRuleProvider 接入真实存储 `[S]`
  - 验收: 构造时传入 SQLite Reader，`get_rules()` 返回正确三层规则
  - 文件: `packages/data/src/ditto_data/services/strategy/instrument_rule_provider.py`
  - 测试: 更新 `test_instrument_rule_provider_unit.py`

---

## Part 06: 最终验收

- [ ] `pixi run -e dev check` 通过
- [ ] `pixi run -e dev ci` 通过
- [ ] 分支覆盖率 >= 80%
- [ ] `pixi run -e dev arch-check` 通过

---

## 不在本 Sprint 范围

以下为 Phase 8 Backlog，不在本轮规划内：

| 项目 | 优先级 | 说明 |
|------|--------|------|
| portfolio/sizing.py (RiskSizer) | P3 | Mean-Variance / Risk Parity |
| Walk-Forward 参数优化 | P3 | Phase 8 |
| 多策略资金预算 | P3 | Phase 8 |
| MarginAccountBuyingPower | P3 | Phase 8 |
| v4 事件账本架构 | P3 | 附录 C |

---

## 依赖关系

```
Part 01 (提交收尾)
  └─→ Part 02 (导出补全) ─ 可并行
  └─→ Part 03 (artifact 序列化) ─ 可并行
  └─→ Part 04 (Catalog 存储) ─ 可并行
  └─→ Part 05 (Rule 存储) ─ 可并行

Part 04 + Part 05 ──→ Part 06 (最终验收)
```

**Part 02-05 互相独立，可并行执行。**

## 工时估算

| Part | 任务数 | 复杂度 | 估算 |
|------|--------|--------|------|
| Part 01 | 1 (commit) | S | ~10 min |
| Part 02 | 1 | S | ~15 min |
| Part 03 | 2 | M + S | ~1h |
| Part 04 | 3 | M + M + S | ~2h |
| Part 05 | 3 | M + M + S | ~2h |
| Part 06 | 1 (验收) | S | ~15 min |
| **总计** | **11** | | **~5.5h** |
