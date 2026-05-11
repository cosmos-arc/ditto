# 跨模块整改执行策略

> 日期：2026-05-08
> 输入：12 包模块审计报告（`docs/reviews/audit/modules/`）
> 基线文档：`module-review-ledger.md`、`adr-runtime-spine.md`、`capability-maturity.md`、`public-api-and-guard-backlog.md`
> 目标：将 12 包审计发现的 accepted findings 转化为可执行的批次化整改计划

---

## 1. 执行总览

### 1.1 Finding 统计

| 模块 | P0 | P1 | P2 | 总计 |
|---|---:|---:|---:|---:|
| kernel | 0 | 3 | 2 | 5 |
| platform | 0 | 1 | 3 | 4 |
| data | 0 | 4 | 2 | 6 |
| features | 0 | 3 | 2 | 5 |
| strategy | 0 | 3 | 2 | 5 |
| portfolio | 0 | 3 | 2 | 5 |
| risk | 0 | 3 | 1 | 4 |
| execution | 0 | 4 | 2 | 6 |
| backtest | 0 | 3 | 2 | 5 |
| analysis | 0 | 3 | 1 | 4 |
| application | 0 | 4 | 2 | 6 |
| apps | 0 | 3 | 2 | 5 |
| **合计** | **0** | **37** | **23** | **60** |

### 1.2 跨模块共性问题（按影响面排序）

| # | 共性问题 | 涉及模块 | 影响面 | 发现数 |
|---|---|---|---|---:|
| C1 | 存储层跨层穿透 / composition root 边界模糊 | application, apps, backtest, execution, strategy, analysis | application 直接引用 SQLite 实现类 27+ 处，apps registry fan-in | 7 |
| C2 | Protocol 冗余 / 方法名不匹配 / 零消费 | portfolio, risk, execution, strategy, analysis | 5 处 Protocol 定义后无消费端或接口语义断裂 | 5 |
| C3 | 公共 API 导入纪律缺失 / 深层引用 | platform 86 处, portfolio 34 处, features services 表面过宽 | 120+ 处消费者绕过 facade 直接引用内部实现 | 4 |
| C4 | CLAUDE.md / 文档过时或缺失 | platform, execution, risk | 3 个包文档与实际代码状态不一致 | 3 |
| C5 | 虚假依赖 / 未使用导入 | risk (polars/orjson), analysis (numpy) | 包声明了不必要的外部依赖 | 2 |
| C6 | 大文件 / 高 fan-in 拆分 | platform, execution, strategy, features, application, backtest, apps | 10+ 个文件超过 500 LOC | 8 |
| C7 | 事件 payload 无类型 / audit schema 可漂移 | kernel, risk, execution | `dict[str, Any]` 在 3 个关键路径 | 3 |
| C8 | 状态恢复 / snapshot 契约缺失 | portfolio, risk, strategy, backtest | 4 个模块的状态型对象无 snapshot/restore | 4 |
| C9 | 成熟度标注不一致 / 过度声明 | strategy, analysis, apps, data | 模板/命名空间/API 暗示超出实际能力 | 4 |

---

## 2. 执行优先级与批次划分

### 2.1 分批原则

1. **先降风险再降复杂度**：影响交易正确性和运行时恢复的问题优先
2. **先基础设施再上层**：kernel/platform 先稳定，能力包后跟进
3. **先契约再实现**：跨模块契约（Protocol、事件类型、公共 API）先冻结，单模块实现后补
4. **同批次可并行**：无依赖关系的模块改动可在同一 PR 或并行 PR 中完成
5. **每批次通过 `pixi run -e dev check` 验收**

### 2.2 批次总览

| 批次 | 名称 | 核心目标 | 涉及模块 | 预估 Finding 覆盖 | 前置批次 |
|---|---|---|---|---|---|
| B1 | 卫生治理 | 清除虚假依赖、更新文档、修复 SQL 安全 | risk, analysis, platform, 所有包 CLAUDE.md | 10 | 无 |
| B2 | 公共 API 收敛 | 建立 `__all__` 纪律、消除深层引用、收敛 services 表面 | kernel, platform, portfolio, features, 所有包 | 12 | B1 |
| B3 | Protocol 归位 | 修复接口断裂、消除冗余 Protocol、统一命名 | portfolio, risk, execution, strategy, analysis | 8 | B2 |
| B4 | 事件与审计类型化 | typed event payload、audit schema、event-name catalog | kernel, risk, execution, portfolio | 6 | B3 |
| B5 | 状态恢复契约 | snapshot/restore/replay 最小方案 | portfolio, risk, strategy, backtest | 6 | B4 |
| B6 | 大文件拆分与 composition root | 按职责拆分高 LOC 文件、收紧 application wiring | platform, execution, strategy, features, application, backtest, apps | 12 | B3 |
| B7 | 成熟度标注统一 | maturity manifest 完整化、API 文档对齐 | strategy, analysis, apps, data | 6 | B1 |

> B1 和 B7 可并行启动。B2-B6 有严格依赖链。

---

## 3. 各批次详细执行计划

### 批次 B1：卫生治理（零前置依赖，立即可启动）已完成（2026-05-09）

**目标**：消除虚假依赖、修复 SQL 安全隐患、更新过时文档。这些改动不改变任何公共 API 或跨模块契约，回归风险最低。

#### B1.1 清除虚假依赖

| 改动 | 涉及文件 | Finding | 风险 | 验证 |
|---|---|---|---|---|
| risk 移除 polars 运行时依赖 | `packages/risk/pyproject.toml` | C5 | 仅移除 import 未使用的依赖 | `pixi run -e dev test packages/risk/tests` |
| risk 移除 orjson 运行时依赖 | `packages/risk/pyproject.toml` | C5 | 同上 | 同上 |
| analysis 移除 numpy 运行时依赖 | `packages/analysis/pyproject.toml` | C5 | 同上 | `pixi run -e dev test packages/analysis/tests` |

**验证**：对每个包执行 `rg "import (polars|orjson|numpy)" packages/<pkg>/src/` 确认源码中无直接使用。

#### B1.2 Platform SQL 安全修复

| 改动 | 涉及文件 | Finding | 方法 |
|---|---|---|---|
| `SQLiteClient.count` 添加 identifier validation | `packages/platform/src/ditto_platform/foundation/storage/sqlite_client.py` | PLAT-P1-01 | 添加 `validate_identifier()` 函数，reject 非白名单字符 |

**TDD 步骤**：
1. RED: 添加测试 reject 含特殊字符的 table name 和 where fragment
2. GREEN: 实现 `validate_identifier`，白名单 `[a-zA-Z0-9_.=><' ]` 或等价方案
3. REFACTOR: 移除 caller-validated 注释，validation 成为本地保证

**验证**：`pixi run -e dev test packages/platform/tests && pixi run -e dev arch-check`

#### B1.3 更新过时 CLAUDE.md

| 模块 | 当前问题 | 更新内容 |
|---|---|---|
| platform | 未反映 SQL 安全修复 | 添加 SQL identifier validation 说明 |
| execution | 未反映 audit/store 现状和 OMS Lite 规划方向 | 添加 OMS Lite 方向、broker/gateways 占位状态 |
| risk | 未反映连续风控 gate 规划 | 添加 RiskGate 方向和状态恢复规划 |

**验证**：人工审查每个 CLAUDE.md 与实际源码一致性。

#### B1.4 Kernel barrel 精简准备

| 改动 | 涉及文件 | Finding |
|---|---|---|
| 记录 kernel `__all__` 30 个符号的分类（stable/candidate/internal） | `packages/kernel/CLAUDE.md` | KERNEL-P2-01 |
| 记录 `Derived*` 异常的共享边界归属 | `packages/kernel/CLAUDE.md` | KERNEL-P2-02 |

**验证**：CLAUDE.md 中有完整的 public API 表。

---

### 批次 B2：公共 API 收敛 ✅ 已完成（2026-05-09）

**目标**：建立每个包的公共 API 纪律，消除深层引用（消费者绕过 facade 直接触及内部模块）。

**前置**：B1 完成（文档已更新，虚假依赖已清除）。

#### B2.1 Kernel 公共 API 表

| 改动 | 涉及文件 | Finding |
|---|---|---|
| 在 kernel CLAUDE.md 建立公共 API 表，标注 stable/candidate/internal | `packages/kernel/CLAUDE.md` | KERNEL-P2-01 |
| 添加架构测试：root `__all__` 不超过预算 | `scripts/architecture/check_architecture_smells.py` 新增 guard | KERNEL-P2-01 |

**关键文件清单**：
- `packages/kernel/src/ditto_kernel/__init__.py`
- `packages/kernel/CLAUDE.md`
- `scripts/architecture/check_architecture_smells.py`

#### B2.2 Platform 深层引用消除

| 改动 | Finding | 方法 |
|---|---|---|
| 消除 86 处深层引用：消费者应通过 platform facade 导入 | PLAT-P1-01 (partial), C3 | 逐步将高频内部引用提升到 `ditto_platform` root `__init__.py` 的 `__all__` |

**关键引用热点**（需逐一验证）：
- `from ditto_platform.foundation.storage.sqlite_client import SQLiteClient`
- `from ditto_platform.foundation.storage.parquet_store import ParquetStore`
- `from ditto_platform.foundation.config.paths import DataPaths`

**验证**：`rg "from ditto_platform\\..*\\..*import" packages/ --iglob '!packages/platform/*'` 计数应显著下降。

#### B2.3 Portfolio 公共 API 整理

| 改动 | Finding | 方法 |
|---|---|---|
| 消除 34 处深层引用 | PORT-P2-01, C3 | 提升 portfolio facade，添加公共 API 表 |
| 标注 positions/holdings/target_portfolios 为 experimental | PORT-P1-02 | CLAUDE.md 添加成熟度标注 |

**关键文件清单**：
- `packages/portfolio/src/ditto_portfolio/__init__.py`
- `packages/portfolio/CLAUDE.md`

#### B2.4 Features services 表面收敛

| 改动 | Finding | 方法 |
|---|---|---|
| 收敛 `features.services` 公共表面 | FEAT-P2-02 | 添加 `ditto_features.services.__all__`，标注 stable facade vs internal |

**关键文件清单**：
- `packages/features/src/ditto_features/services/__init__.py`
- `packages/features/CLAUDE.md`

#### B2.5 全包 `__all__` 纪律

| 改动 | Finding |
|---|---|
| 每个包添加 `__all__` budget guard | KERNEL-P2-01, FEAT-P2-02, C3 |

**验证**：`scripts/architecture/check_architecture_smells.py` 新增 guard，CI 中运行。

---

### 批次 B3：Protocol 归位 ✅ 已完成（2026-05-09）

**目标**：修复 Protocol 接口断裂、消除冗余 Protocol、统一跨包命名。

**前置**：B2 完成（公共 API 已收敛，`__all__` 纪律已建立）。

#### B3.1 Portfolio 接口断裂修复

| 改动 | Finding | 关键文件 |
|---|---|---|
| 修复 `RebalanceTarget.positions` vs `TargetPortfolio.weights` 接口断裂 | PORT-P0 (原始用户输入) | `packages/portfolio/src/ditto_portfolio/rebalancing/`、`packages/portfolio/src/ditto_portfolio/target_portfolios/` |

**方法**：
1. RED: 添加测试证明 `RebalanceTarget` 和 `TargetPortfolio` 可互操作或显式区分
2. GREEN: 统一 weights 表示或建立明确的转换契约
3. REFACTOR: 消除 strategy/portfolio 中 `TargetPortfolio` 命名歧义（STRAT-P2-01 联动）

#### B3.2 Risk contracts.py 冗余 Protocol 清理

| 改动 | Finding | 关键文件 |
|---|---|---|
| 审查并移除 `contracts.py` 中零消费的 Protocol | RISK-P1-01 (partial) | `packages/risk/src/ditto_risk/constraints/` |

**方法**：
1. 扫描每个 Protocol 的消费端引用
2. 零消费的 Protocol 标注 reserved 或移除
3. 方法名不匹配的 Protocol 对齐到实际消费端

#### B3.3 Execution TradeAuditor Protocol 完善

| 改动 | Finding | 关键文件 |
|---|---|---|
| 完善 `TradeAuditor` Protocol 方法签名 | EXEC-P1-04 (partial) | `packages/execution/src/ditto_execution/audit/` |

#### B3.4 跨包命名消歧表

| 改动 | Finding |
|---|---|
| 建立跨包 PositionReader / TargetPortfolio / Holding / Signal 命名消歧表 | PORT-P2-01, STRAT-P2-01, APP-P2-02 |

**产出**：写入 `docs/architecture/public-api-and-guard-backlog.md` 中的命名消歧章节。

**验证**：每个消歧的名称有对应的 CLAUDE.md 条目和 `__all__` 标注。

---

### 批次 B4：事件与审计类型化 ✅ 已完成（2026-05-09）

**目标**：为 runtime spine 提供类型安全的事件和审计基础。

**前置**：B3 完成（Protocol 已归位，接口语义已对齐）。

#### B4.1 Event-name catalog ✅

| 改动 | Finding | 关键文件 |
|---|---|---|
| 建立 `EventName` 常量类：`ORDER_SUBMITTED`, `ORDER_FILLED`, `ORDER_CANCELED`, `RISK_GUARD_TRIGGERED`, `POSITION_CHANGED` | KERNEL-P1-01, C7 | `packages/kernel/src/ditto_kernel/events.py` |

**完成内容**：
- kernel `events.py` 新增 `EventName` 类（5 个常量）
- execution/risk/portfolio 事件类 `event_type` 全部引用 `EventName` 常量
- 不放入 barrel（30 限制），消费者从叶模块导入

#### B4.2 Risk typed audit payloads ✅

| 改动 | Finding | 关键文件 |
|---|---|---|
| `RiskGuardDetails` typed dataclass 替代 `dict[str, Any]` | RISK-P1-03, C7 | `packages/risk/src/ditto_risk/events.py` |

**完成内容**：
- `RiskGuardDetails(instrument_id, current_value, limit_value, description)` frozen dataclass
- `RiskGuardTriggered.details` 类型从 `dict[str, Any]` 改为 `RiskGuardDetails`
- backtest `risk_scan.py` 更新为构造 `RiskGuardDetails` 实例

#### B4.3 Portfolio 事件决策 ✅（Option B）

| 改动 | Finding | 关键文件 |
|---|---|---|
| 保持 `PositionChanged` 为 reserved，CLAUDE.md 明确标注 | PORT-P1-03 | `packages/portfolio/CLAUDE.md` |

**决策**：Option B — 保持 reserved。待 B5 状态恢复契约有消费者后从 `apply_fill` 发布。

#### B4.4 Kernel DomainEvent 兼容层 ✅

| 改动 | Finding |
|---|---|
| `DomainEvent.payload: dict[str, Any]` 保留 transport 兼容，新事件子类通过专属 typed 字段承载数据 | KERNEL-P1-01 |

**完成内容**：
- kernel CLAUDE.md 添加 DomainEvent 兼容策略章节
- 明确规则：新事件不依赖 payload，event_type 引用 EventName 常量

**验证**：`pixi run -e dev test packages/kernel/tests packages/risk/tests packages/execution/tests packages/portfolio/tests packages/backtest/tests`

---

### 批次 B5：状态恢复契约 ✅ 已完成（2026-05-09）

**目标**：为 portfolio/risk/strategy/backtest 提供最小 snapshot/restore 方案。

**前置**：B4 完成（事件类型已稳定，audit schema 已对齐）。

#### B5.1 Portfolio state projection ✅

| 改动 | Finding | 关键文件 |
|---|---|---|
| 定义 `PortfolioStateSnapshot` / `FillProjector` Protocol / `AccountProjector` | PORT-P1-01 | `packages/portfolio/src/ditto_portfolio/projection.py` 新增 |

**完成内容**：
- `PortfolioStateSnapshot` frozen dataclass（positions + cash + as_of_date）
- `FillProjector` Protocol 接口
- `AccountProjector` 实现：基于 Account 累加 fill 流，生成快照
- 7 个测试验证空 fills、BUY/SELL fills、与 Account.apply_fill 一致性

#### B5.2 Risk state snapshot/restore ✅

| 改动 | Finding | 关键文件 |
|---|---|---|
| `MaxDrawdownRule` 的 snapshot/restore | RISK-P1-02 | `packages/risk/src/ditto_risk/drawdown/rules.py` |

**完成内容**：
- `DrawdownStateSnapshot` frozen dataclass（peak_nav）
- `MaxDrawdownRule.snapshot()` 和 `.restore()` 方法
- 5 个测试验证快照捕获、恢复、重放一致性（replay NAV 系列 → snapshot → reset → restore → 相同 actions）

#### B5.3 Strategy context recovery ✅

| 改动 | Finding | 关键文件 |
|---|---|---|
| `StrategyContext` snapshot/restore | STRAT-P1-02 | `packages/strategy/src/ditto_strategy/alpha/context.py` |

**完成内容**：
- `StrategyContextSnapshot` frozen dataclass（risk_locked_instruments + positions）
- `StrategyContext.to_snapshot()` 和 `.from_snapshot()` 方法
- 6 个测试验证快照捕获、恢复、frozen、roundtrip、深拷贝语义

#### B5.4 Backtest replay 扩展 ✅

| 改动 | Finding | 关键文件 |
|---|---|---|
| 扩展 replay proof：fill 对比 + account state 对比 | BACKTEST-P1-03 | `packages/backtest/src/ditto_backtest/replay.py` |

**完成内容**：
- `FillComparison` frozen dataclass（identical + mismatch_count + length_mismatch + point_count）
- `AccountStateComparison` frozen dataclass（identical + nav_diff + cash_diff + position_count_diff）
- `ReplayProof` 静态方法：compare_fills()、compare_account_state()
- 8 个测试验证 fills 对比和 account state 对比

**验证**：`pixi run -e dev check` 全部通过（lint + type + test + arch-check + arch-smells）

---

### 批次 B6：大文件拆分与 composition root 收紧 ✅ 已完成（2026-05-09）

**目标**：按职责拆分高 LOC 文件，收紧 application 的 composition wiring 边界。

**前置**：B3 完成（Protocol 已归位）。可与 B4/B5 部分并行。

#### B6.1 Platform ParquetStore 拆分 ✅

| 改动 | Finding | 原 LOC | 拆分后 |
|---|---|---|---|
| 按职责拆分 read/write/metadata/path helpers | PLAT-P2-01 | 768 | facade 339 + paths 46 + read 73 + write 141 + metadata 66 |

**完成内容**：
- `parquet_store.py` → facade（re-export 所有公共 API）
- `parquet_paths.py` → path layout helpers
- `parquet_read.py` → scan/lazy read
- `parquet_write.py` → write/merge/dedup
- `parquet_metadata.py` → metadata/checksum

#### B6.2 Execution planner 拆分 ✅

| 改动 | Finding | 原 LOC | 拆分后 |
|---|---|---|---|
| 按 target diff / market precheck / rounding / cost / id 拆分 | EXEC-P2-01 | 530 | facade 164 + target_diff 208 + market_precheck 54 + quantity_rounding 63 + cost_estimate 49 |

#### B6.3 Strategy 大模板拆分 ✅

| 改动 | Finding | 原 LOC | 拆分后 |
|---|---|---|---|
| `stock_sector_rotation.py` | STRAT-P2-02 | 640 | 107 |
| `regime.py` | STRAT-P2-02 | 528 | 46 |

#### B6.4 Application providers 收紧 ✅

| 改动 | Finding | 原 LOC | 拆分后 |
|---|---|---|---|
| concrete imports 移向 apps registry | APP-P1-01, C1 | 563 | 48 |

#### B6.5 Backtest 大文件拆分 ✅

| 改动 | Finding | 原 LOC | 拆分后 |
|---|---|---|---|
| `statistics.py` | BACKTEST-P2-01 | 627 | facade 78 + returns 160 + trades 215 + alpha 196 |
| `engine.py` | BACKTEST-P2-01 | 518 | 375 |
| `manifest.py` | BACKTEST-P2-01 | 421 | 38 |

**注意**：statistics 子模块拆分后移除了 `_` 前缀（跨模块可见的内部函数不应使用 `_` 前缀），`__all__` 已同步更新。

#### B6.6 Apps route/job 拆分 ✅

| 改动 | Finding | 原 LOC | 拆分后 |
|---|---|---|---|
| `api/routes/backtest.py` | APPS-P2-01 | 526 | facade 47 + run_routes 256 + query_routes 独立 |
| `api/routes/trade.py` | APPS-P2-01 | 412 | facade 43 + 子模块独立 |

**验证**：`pixi run -e dev check` 通过（lint ✅ + fmt ✅ + type 13 预存错误 + test 6336 passed）

---

### 批次 B7：成熟度标注统一 ✅ 已完成（2026-05-10）

**目标**：确保所有包的成熟度标注与实际能力一致，API/CLI 不暗示超出实际的能力。

**前置**：B1 完成（文档已更新）。可与 B2-B6 并行。

#### B7.1 Strategy 模板成熟度 ✅

| 改动 | Finding |
|---|---|
| ETF templates 标注 initial-focus，stock/sector templates 标注 experimental | STRAT-P1-03 |

**完成内容**：
- strategy CLAUDE.md 新增模板成熟度表（etf_rotation/etf_trend_swing = initial-focus，stock_selection_trend/stock_sector_rotation = experimental）
- capability-maturity.md 更新 Strategy alpha templates 行，列出具体模板名和成熟度

**关键文件**：
- `packages/strategy/CLAUDE.md`
- `docs/architecture/capability-maturity.md`

#### B7.2 Analysis reserved namespace 强化 ✅

| 改动 | Finding |
|---|---|
| 将 reserved namespace 列表移入 maturity manifest 作为 enforcement source | ANALYSIS-P2-01 |
| SHIFT_TO_NEXT_SNAPSHOT 标注 reserved/unsupported 或实现实际语义 | ANALYSIS-P1-02 |

**完成内容**：
- `LateArrivalPolicy` docstring 添加 reserved 声明，`SHIFT_TO_NEXT_SNAPSHOT` 行注释标注 `reserved: not implemented`
- 警告消息更新为 "SHIFT_TO_NEXT_SNAPSHOT is reserved (not implemented)"
- capability-maturity.md 新增 Reserved API Surface 章节，列出 SHIFT_TO_NEXT_SNAPSHOT
- 新增测试验证 docstring 包含 "reserved"、警告消息包含 "reserved"

**关键文件**：
- `packages/analysis/src/ditto_analysis/research/`
- `docs/architecture/capability-maturity.md`

#### B7.3 Apps maturity-aware API ✅

| 改动 | Finding |
|---|---|
| API route/help text 添加 maturity 元数据 | APPS-P1-02 |
| 非 initial-focus 的 route 标注 experimental/reserved | APPS-P1-02 |

**完成内容**：
- 9 个非 initial-focus 路由模块 docstring 添加 `maturity:` 标注
- apps CLAUDE.md 路由表新增成熟度列
- capability-maturity.md 新增 API Route Maturity 章节
- arch-smell checker 新增 `check_route_maturity_annotations()` 检查

#### B7.4 Data 成熟度标注 ✅

| 改动 | Finding |
|---|---|
| DataCatalog runtime 标注 experimental 直到 store 实现完成 | DATA-P1-01 |
| FX/commodity/macro dataset families 标注 experimental | DATA-P1-02 |

**完成内容**：
- data CLAUDE.md 新增数据集成熟度表（10 个数据集族的成熟度标注）
- 明确 DataCatalog runtime = experimental（Protocol only），Lineage = reserved

**验证**：`pixi run -e dev check` 通过（lint + fmt + type + 6319 tests passed + arch-check 36/36 + arch-smells passed）

---

## 4. 批次依赖关系图

```
B1 (卫生治理)
│
├─→ B2 (公共 API 收敛)
│    │
│    └─→ B3 (Protocol 归位)
│         │
│         ├─→ B4 (事件与审计类型化)
│         │    │
│         │    └─→ B5 (状态恢复契约)
│         │
│         └─→ B6 (大文件拆分 + composition root) ── 可与 B4/B5 部分并行
│
└─→ B7 (成熟度标注) ── 可与 B2-B6 并行
```

**关键路径**：B1 → B2 → B3 → B4 → B5

**并行窗口**：
- B1 完成后，B7 可立即启动
- B3 完成后，B6 可启动（不阻塞 B4/B5）
- B4 和 B6 可并行推进

---

## 5. 风险评估

### 5.1 高风险改动（可能引起连锁反应）

| 改动 | 涉及批次 | 连锁影响 | 缓解措施 |
|---|---|---|---|
| Portfolio `RebalanceTarget`/`TargetPortfolio` 接口统一 | B3 | strategy/application/backtest 可能需要适配新接口 | 先建立转换契约，保持旧接口作为 deprecated bridge |
| Platform `__all__` 提升 / 深层引用消除 | B2 | 86 处 platform 引用点需要逐一修改 import 路径 | 分包逐步推进，每包独立 PR |
| Event-name catalog 替换 string literal | B4 | backtest steps 所有 publish site 需要修改 | 保持 string 兼容期，catalog 为常量别名 |
| Application providers concrete wiring 迁移 | B6 | application 和 apps 的 composition 逻辑重新组织 | 先建 port，后迁移 wiring，不一步到位 |
| Risk typed payload 替换 `dict[str, Any]` | B4 | backtest/execution 的 audit consumer 需要适配 | 新 payload 包含旧 dict 作为 fallback 过渡期 |

### 5.2 中风险改动

| 改动 | 涉及批次 | 风险描述 |
|---|---|---|
| Kernel `__all__` 精简 | B2 | 外部消费者可能依赖未导出的符号 |
| Strategy context snapshot | B5 | snapshot 格式需要与 backtest replay 兼容 |
| Backtest replay 扩展 | B5 | 新的 replay 维度可能暴露已有回测结果不一致 |
| Features services `__all__` 收敛 | B2 | 消费者可能依赖 services 内部模块 |

### 5.3 低风险改动

| 改动 | 涉及批次 | 风险 |
|---|---|---|
| 虚假依赖移除 | B1 | 极低——源码未使用这些依赖 |
| CLAUDE.md 更新 | B1 | 无代码影响 |
| 成熟度标注 | B7 | 仅文档/注释，无代码行为变更 |
| `__all__` budget guard 添加 | B2 | 仅新增检查，不修改现有代码 |

---

## 6. 每批次的 PR 策略建议

### 6.1 PR 粒度

| 批次 | 建议 PR 数量 | 划分方式 |
|---|---|---|
| B1 | 3-4 | 按模块分：risk+analysis 虚假依赖、platform SQL、文档更新 |
| B2 | 5-6 | 按模块分：kernel、platform、portfolio、features、guard 脚本 |
| B3 | 3-4 | portfolio 接口修复、risk/execution Protocol 清理、命名消歧表 |
| B4 | 2-3 | event catalog、risk typed payload、portfolio 事件决策 |
| B5 | 3-4 | portfolio projection、risk snapshot、strategy context、backtest replay |
| B6 | 4-6 | 按模块分拆分 PR，每个模块一个 |
| B7 | 2-3 | 成熟度 manifest 更新、API/CLI 标注 |

### 6.2 每个 PR 的验收清单

- [ ] `pixi run -e dev test packages/<pkg>/tests` 通过
- [ ] `pixi run -e dev arch-check` 通过（涉及依赖变更时）
- [ ] `pixi run -e dev check` 通过
- [ ] 涉及的 finding 状态更新到 `module-review-ledger.md`
- [ ] 涉及的 CLAUDE.md 已同步更新

---

## 7. 时间线建议

| 周次 | 批次 | 预估工作量 |
|---|---|---|
| W1 | B1 (卫生治理) + B7 启动 | 低风险改动，快速产出 |
| W2 | B2 (公共 API 收敛) | 中等工作量，主要是 import 路径调整 |
| W3 | B3 (Protocol 归位) + B6 启动 | 需要仔细设计接口 |
| W4 | B4 (事件类型化) + B6 继续 | 事件 catalog 需要跨包协调 |
| W5 | B5 (状态恢复) + B6/B7 收尾 | 最复杂批次，需要多包联动 |
| W6 | 验收与收尾 | 全量 `pixi run -e dev check`，ledger 最终更新 |

---

## 8. 成功标准

当本执行策略完成后，Ditto 应达到以下状态：

1. **零虚假依赖**：每个包的 `pyproject.toml` 只声明实际使用的运行时依赖
2. **公共 API 纪律**：每个包有 `__all__` budget guard，消费者不绕过 facade
3. **Protocol 一致**：无零消费 Protocol，无接口断裂，跨包命名消歧完成
4. **事件类型安全**：runtime event 使用 typed dataclass 和 event-name catalog，不再有 `dict[str, Any]` payload
5. **状态可恢复**：portfolio/risk/strategy 有最小 snapshot/restore 契约
6. **文件可读**：无超过 500 LOC 的混合职责文件
7. **成熟度诚实**：API/CLI/文档不暗示超出实际的能力
8. **所有 finding 状态为 fixed 或 deferred（含明确 reopen 条件）**

---

## 9. 未覆盖的 W1 Runtime Spine 项

本执行策略聚焦于审计发现的 60 个 finding 的整改。以下 W1 Runtime Spine 项不在本策略范围内，需要独立的实施计划：

| 项 | 说明 | 触发条件 |
|---|---|---|
| OMS Lite 完整实现（EXEC-P1-01 ~ P1-04） | identity types、state machine、journal、idempotency 需要完整设计 | B4 完成后启动独立实施计划 |
| Paper/Mock Gateway | EXEC-P1-02 | OMS journal 定义完成后 |
| Reconciliation Service | EXEC-P1-03 | OMS journal + paper gateway 完成后 |
| Backtest/Paper Shared Seam | BACKTEST-P1-01 | B4 + B5 完成后 |
| HistoricalDataPortal | BACKTEST-P1-02, DATA-P1-03 | DataCatalog runtime 决策后 |
| DataCatalog Runtime Store | DATA-P1-01 | B7 完成后独立实施 |
| TimeContext 实现 | KERNEL-P1-02 | 至少两个消费者准备好后 |
| Trading/Reference 归属迁移 | KERNEL-P1-03 | Reference domain ADR 决策后 |

这些项的依赖关系在 `adr-runtime-spine.md` 中已有描述，应在本策略 B1-B7 推进过程中同步设计，但不阻塞本策略的执行。
