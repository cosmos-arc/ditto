# 策略引擎 v3 剩余任务开发计划

> **SUPERSEDED** — 本计划中的任务已全部被治理收口计划 (`2026-03-24-strategy-engine-v3-governance-closeout-plan.md`) 覆盖并完成。P0 ExecutionAuditService (Task 1)、P2 Port 层 Service (Task 6-7) 等均已实现。

## 概述

- Sprint: Phase 4 收尾 | 范围: P0 + P1 + P2
- 创建: 2026-03-24
- 基于: `docs/plans/2026-03-24-strategy-engine-v3-completion-analysis.md` 代码审计结果

### 关键发现

分析文档存在过时信息：**RunManifest + RuleRefs 已在 `d56e1624` 提交中完整实现**（含 RuleRefCollector、engine.py 集成、591 行集成测试），实际完成度 ~97% 而非文档声称的 ~95%。本计划将此项排除。

### 剩余任务全景

| 优先级 | 任务 | 复杂度 | 依赖 |
|--------|------|--------|------|
| P0 | ExecutionAuditService（SQLite） | M | T-5, T-6 |
| P1 | BacktestReport 补齐 risk_log/pre_trade_log | S | 无 |
| P1 | 确定性回放测试 S4 两层完善 | M | 无 |
| P1 | FLAT_TO_FLAT TradeBuilder 实现 | S | 无 |
| P1 | RiskScanRecord 字段类型 str→枚举 | S | 无 |
| P1 | order_book.py 非 dataclass 注释 | S | 无 |
| P2 | audit/ 子目录拆分 | M | 无 |
| P2 | Account.apply_fill() 独立方法 | S | 无 |
| P2 | Port 层 Service 实现 | L | T-5 |

---

## 技术方案

### 1. ExecutionAuditService 存储策略

**决策：SQLite 持久化**

- 使用现有 `SQLitePool`（`ditto_infra.foundation`）
- 建表 `execution_audit` 存储 `risk_log` + `pre_trade_log` 记录
- 索引：`(run_id, trade_date, record_type)`
- 与 `StrategyArtifactService` 解耦，独立存储审计流水

**表结构设计**：

```sql
CREATE TABLE execution_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT    NOT NULL,
    trade_date  TEXT    NOT NULL,
    record_type TEXT    NOT NULL,  -- 'risk_scan' | 'pre_trade_decision'
    instrument_id TEXT,
    payload     TEXT    NOT NULL,  -- JSON (orjson 序列化)
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_run_date ON execution_audit(run_id, trade_date);
CREATE INDEX idx_audit_run_type ON execution_audit(run_id, record_type);
```

### 2. audit/ 子目录拆分方案

当前 `statistics.py` 898 行，职责混合（统计计算 + 审计收集 + 审计记录定义）。

**拆分后**：

```
backtest/
├── audit/
│   ├── __init__.py          # re-export
│   ├── records.py           # RiskScanRecord, PreTradeDecisionRecord
│   └── collector.py         # ExecutionAuditCollector（recording + getter）
├── statistics.py            # 统计数据类 + 计算逻辑 + 辅助函数
└── ...
```

**关键决策**：`ExecutionAuditCollector` 的 `build_report()` 和计算方法保留在 `statistics.py`，通过 `build_report()` 接收 collector 实例参数。collector 只负责记录和获取原始数据。

### 3. FLAT_TO_FLAT TradeBuilder 算法

- 按品种累计买卖成交量、成交额、费用
- 净仓位归零时产出单笔 `TradeRecord`（VWAP entry/exit）
- 未平仓部分通过 `flush()` 输出
- 复用现有 `TradeBuilder` Protocol 和 `TradeRecord` 数据类

### 4. Port 层 Service 架构

```
apps/port/services/strategy/
├── __init__.py
├── input_assembler.py       # StrategyInputBundle 组装（从 EngineLoop 提取）
├── backtest_service.py      # BACKTEST 模式编排
└── strategy_run_service.py  # RESEARCH/RECOMMENDATION 编排
```

依赖链：`input_assembler` ← `backtest_service` ← `strategy_run_service`

---

## 任务清单

### Phase 1: Foundation（无依赖，可并行）

- [x] **T-1: RiskScanRecord 字段类型升级** `[S]` ✅
  - 验收: `severity` 使用 `RiskSeverity`，`action_taken` 使用 `RiskActionType`；engine.py 构造处移除 `.value`；所有测试更新
  - 文件: `packages/core/src/ditto_core/backtest/statistics.py`, `packages/core/src/ditto_core/backtest/engine.py`
  - 测试: 单元测试（构造函数类型验证）
  - 风险: 无（StrEnum 行为兼容 str）

- [x] **T-2: BacktestReport 补齐 risk_log / pre_trade_log 字段** `[S]` ✅
  - 验收: `BacktestReport` 新增 `risk_log: tuple[RiskScanRecord, ...]` 和 `pre_trade_log: tuple[PreTradeDecisionRecord, ...]`；`build_report()` 填充这两个字段
  - 文件: `packages/core/src/ditto_core/backtest/statistics.py`
  - 测试: 单元测试（build_report 输出包含新字段）
  - 风险: 无（纯增量字段）

- [x] **T-3: order_book.py 非 dataclass 注释** `[S]` ✅
  - 验收: `OrderBook` 类 docstring 说明选择普通 class 原因（mutable state、OrderBook 管理生命周期）
  - 文件: `packages/core/src/ditto_core/strategy/accounting/order_book.py`
  - 测试: 无需新测试
  - 风险: 无

- [x] **T-4: FLAT_TO_FLAT TradeBuilder 实现** `[S]` ✅
  - 验收: `FlatToFlatTradeBuilder` 实现 `TradeBuilder` Protocol；按品种 VWAP 匹配；净仓位归零时输出 `TradeRecord`；`flush()` 处理未平仓；`EngineConfig.trade_matching` 支持 `"flat_to_flat"`；EngineLoop 工厂方法实例化正确 builder
  - 文件: `packages/core/src/ditto_core/execution/trade_builder.py`, `packages/core/src/ditto_core/backtest/engine.py`
  - 测试: 单元测试（多买一卖、一买多卖、部分平仓、flush、多品种隔离）

### Phase 2: Audit Infrastructure

- [x] **T-5: audit/ 子目录拆分** `[M]` ✅
  - 验收: `backtest/audit/` 目录创建；`records.py` 包含 `RiskScanRecord` + `PreTradeDecisionRecord`；`collector.py` 包含 `ExecutionAuditCollector`（仅 recording + getter API）；`statistics.py` 保留统计数据类 + 计算方法 + 辅助函数；`__init__.py` re-export 保持向后兼容；所有 import 更新；3763+ 测试通过
  - 文件: `packages/core/src/ditto_core/backtest/audit/`（新目录 3 文件）, `packages/core/src/ditto_core/backtest/statistics.py`, `packages/core/src/ditto_core/backtest/__init__.py`
  - 测试: 现有测试全量回归
  - 风险: import 路径变更影响面（需 Grep 全量检查）

- [x] **T-6: ExecutionAuditService（SQLite）** `[M]` ✅
  - 验收: DataHub `services/audit/execution_audit_service.py` 实现；SQLite 表 `execution_audit` 建表 + 读写；`save_risk_log(run_id, records)` + `save_pre_trade_log(run_id, records)` + `query(run_id, record_type?, date_range?)` 方法；orjson 序列化 payload；`StrategyArtifactService` 无耦合
  - 文件: `packages/data/src/ditto_data/services/audit/execution_audit_service.py`（新文件）, `packages/data/src/ditto_data/services/audit/__init__.py`（新文件）
  - 测试: 单元测试（CRUD + 查询过滤）；集成测试（SQLite 写入 + 读取验证）
  - 风险: Schema 变更（+1 级 PIT）；需要数据库 migration 路径
  - 依赖: T-1（RiskScanRecord 类型已升级）, T-2（BacktestReport 已含审计字段）

### Phase 3: Quality & Testing

- [x] **T-7: 确定性回放测试 S4 两层完善** `[M]` ✅
  - 验收: Layer 1 新增 `nav_series` 全量比较测试；Layer 2 实现 `compute_run_diff()` 工具函数（输出 `affected_instruments`, `affected_dates`, 量化差异）；`EngineConfig` 支持 `engine_version` 字段；diff 测试使用版本标签
  - 文件: `packages/core/tests/integration/backtest/test_reproducibility.py`, `packages/core/src/ditto_core/backtest/engine.py`（EngineConfig）
  - 测试: 集成测试（Layer 1 + Layer 2）
  - 风险: 无

### Phase 4: Application Layer

- [x] **T-8: Account.apply_fill() 独立方法** `[S]` ✅
  - 验收: `Account` 新增 `apply_fill(fill, settle_date)` 方法；从 `BacktestBrokerage` 提取 `_update_position()` + `_update_cash()` 逻辑（~80 行）；frozen quantities 追踪保留在 Brokerage（通过参数传入）；Brokerage 调用 `account.apply_fill()` 而非直接操作
  - 文件: `packages/core/src/ditto_core/strategy/accounting/account.py`, `packages/core/src/ditto_core/execution/brokerage.py`
  - 测试: 单元测试（apply_fill 买入/卖出/部分平仓/费用计算）
  - 风险: 涉及交易逻辑（+1 级 Kill Switch）；frozen quantities 状态管理

- [x] **T-9a: StrategyInputAssembler** `[M]` ✅
  - 验收: 从 `EngineLoop._build_input_bundle()` 提取为独立类；接收 DataHub 服务获取市场数据、信号值；产出 `StrategyInputBundle`；可复用于 BACKTEST / RESEARCH / RECOMMENDATION 模式
  - 文件: `apps/port/src/ditto_port/services/strategy/input_assembler.py`（新文件）
  - 测试: 单元测试（mock DataHub，验证 bundle 组装逻辑）
  - 依赖: 无

- [x] **T-9b: BacktestService** `[M]` ✅
  - 验收: Port 层编排服务；加载 StrategySpec（via StrategyCatalogService）；组装输入（via StrategyInputAssembler）；配置 + 运行 EngineLoop；持久化 BacktestReport（via StrategyArtifactService）；持久化审计日志（via ExecutionAuditService）
  - 文件: `apps/port/src/ditto_port/services/strategy/backtest_service.py`（新文件）
  - 测试: 集成测试（端到端 BACKTEST 流程）
  - 依赖: T-5（ExecutionAuditService）, T-9a（StrategyInputAssembler）

- [x] **T-9c: StrategyRunService** `[M]` ✅
  - 验收: Port 层编排服务；RESEARCH 模式：单日信号生成 + 输出；RECOMMENDATION 模式：信号持久化 + 推送；复用 StrategyInputAssembler
  - 文件: `apps/port/src/ditto_port/services/strategy/strategy_run_service.py`（新文件）
  - 测试: 单元测试 + 集成测试
  - 依赖: T-9a（StrategyInputAssembler）

---

## 执行顺序 & 依赖图

```
Phase 1 (并行)          Phase 2 (顺序)        Phase 3         Phase 4
─────────────          ──────────────        ───────         ───────

T-1 RiskScanRecord ─┐
                     ├─→ T-5 audit/拆分 ─→ T-6 ExecutionAuditService ─┐
T-2 BacktestReport ─┘                                               ├─→ T-9b BacktestService
                                                                       │
T-3 order_book 注释                                                    │
                                                                       │
T-4 FLAT_TO_FLAT        T-7 确定性回放 ────────────────────────────────┤
                                                                       │
T-8 Account.apply_fill ────────────────────────────────────────────────┤
                                                                       │
T-9a InputAssembler ─────────────────────────────────────────┬─────────┤
                                                             ├─→ T-9c StrategyRunService
                                                             └────────→ T-9b
```

### 关键路径

```
T-1 → T-5 → T-6 → T-9b（最长链）
```

### 并行机会

- **Phase 1**: T-1, T-2, T-3, T-4 完全可并行
- **Phase 2**: T-5 和 T-7 可并行
- **Phase 4**: T-8, T-9a 可并行；T-9b 和 T-9c 在 T-9a 完成后可并行

---

## 验收门禁

每个 Phase 完成后运行：

```bash
pixi run -e dev check    # lint + fmt + type + test --fast
pixi run -e dev arch-check  # 分层边界检查
```

### 最终验收标准

- [x] basedpyright 类型检查 0 errors
- [x] ruff 检查 All checks passed
- [x] 3954 单元测试全量通过（新增 ~191 测试），3936 fast tests 0 failures
- [x] 分支覆盖率 ≥ 80%
- [x] arch-check 分层边界通过
- [x] ExecutionAuditService SQLite 读写集成测试通过
- [x] FLAT_TO_FLAT 回测与 FIFO 结果可区分
- [x] 确定性回放 Layer 1 + Layer 2 测试通过
