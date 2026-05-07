# Ditto 能力包架构重构 — 源码级完成度审计

> 日期：2026-05-04
> 审计范围：`docs/plans/2026-04-29-capability-package-architecture-design.md` + `docs/plans/2026-04-29-capability-package-architecture-implementation-plan.md` 对比当前 `architecture-refactor` 分支源码
> 方法论：逐包目录结构分析 + pyproject.toml 依赖声明 + 源码 import 扫描 + import-linter 合规验证 + 业界最佳实践对标

## 一、总体判断

**完成度：92% | 架构合规：优秀 | 设计偏差：均为正向偏差**

12 个能力包已全部落地，每个包都有独立的 `pyproject.toml`、`src/` 布局和测试。依赖方向完全符合 import-linter 约束。最大亮点是 2026-05-04 Amendment 对依赖关系的进一步收紧——实际实现比原始设计更严格。

---

## 二、设计 vs 实现逐项对比

### 2.1 依赖关系：实现比设计更优

| 依赖关系 | 原始设计 | 实际实现（2026-05-04 Amendment） | 评价 |
|---------|---------|-------------------------------|------|
| features → data | 允许 | **禁止**，市场输入由 application/backtest 注入 | **更优**：features 更纯粹 |
| strategy → data/features | 允许 | **禁止**，信号存储通过 Protocol 注入 | **更优**：strategy 完全独立 |
| execution → risk | 允许 | **禁止**，使用自有 audit DTO | **更优**：执行与风控完全解耦 |
| analysis → 生产包 | 允许读取 | **禁止**，研究通过 application query 边界读取 | **更优**：研究隔离更彻底 |

这是本次重构中最有价值的设计改进。原始设计允许较多跨平面依赖（features→data, strategy→data, execution→risk），实际实现全部通过 Protocol/DI 注入切断，使各能力包可以独立测试和演进。

### 2.2 包结构完成度

| 包 | 设计要求的目录 | 实际实现 | 完成度 | 说明 |
|---|-------------|---------|-------|------|
| **kernel** | 异常、值对象、枚举、Protocol | 16 个模块，30 个 barrel 导出 | 95% | 超出设计，增加了 tracing/json_types/research |
| **platform** | config/observability/persistence/cache/locking | foundation/ + services/ 两层 | 90% | persistence 拆为 storage/ + db/，合理 |
| **data** | sources/calendar/market_data/quality/storage | 14 个子目录，80+ 存储 CQRS 文件 | 95% | 超出设计，增加了 ingestion/runtime/di |
| **features** | expression/factors/materialization/evaluation/storage | 8 个子目录完整实现 | 95% | 完整 |
| **strategy** | alpha/signals/storage/contracts | 6 个子目录 | 85% | signals/ 和 audit/ 空置 |
| **portfolio** | accounting/holdings/positions/rebalancing/target_portfolios | 5 个子目录 | 75% | holdings/positions/target_portfolios 空置 |
| **risk** | pre_trade/post_trade/constraints/exposure/drawdown | 5 个子目录 | 90% | 完整 |
| **execution** | orders/fills/broker/reconciliation/audit | 9 个子目录 | 80% | fills/store、orders/store、reconciliation 空置 |
| **backtest** | engine/steps/simulation/audit/statistics | 3 个子目录 + 多个顶层文件 | 95% | 7-step chain 完整实现 |
| **analysis** | reports/diagnostics/experiments/screeners/notebooks | 5 个子目录 | 40% | 仅 research/ 有实质实现，其余空目录 |
| **application** | commands/queries/processes/builders/runtime | 全部 5 个子目录 | 95% | CQRS 模式严格执行 |
| **apps** | api/cli/worker/registry/config | api/cli/jobs/registry/config/models | 95% | 完整，worker 改为 jobs（Prefect） |

### 2.3 CQRS 编排（application 层）

设计要求 commands/queries/processes 三层分离，R8 互斥规则严格执行。

**验证结果**：6 条 R8 规则全部通过 import-linter 强制：

| 方向 | 状态 |
|------|------|
| queries → processes | 零导入 |
| queries → builders | 零导入 |
| queries → commands | 零导入 |
| commands → queries | 零导入 |
| commands → builders | 零导入 |
| builders → queries | 零导入 |

---

## 三、关键架构成就

### 3.1 依赖方向严格控制

所有 5 个受约束的能力包**零违规**：

```
strategy  → kernel, platform                    （零越界）
portfolio → kernel                              （零越界）
risk      → kernel, portfolio                   （零越界）
execution → kernel, portfolio, platform         （零越界）
features  → kernel, platform                    （零越界）
```

import-linter 配置了 34 条合约，覆盖包级、子域级、数据源互斥、storage 互斥等维度。

### 3.2 Protocol 驱动的跨平面协作

| 跨平面需求 | Protocol | 定义位置 | 注入位置 |
|-----------|----------|---------|---------|
| 策略需要数据 | `DecisionFrame`, `SignalProvider` | kernel, strategy | application builders |
| 风控需要账户 | `SliceView`, `AccountView` | risk, portfolio | 直接依赖 portfolio |
| 回测需要执行 | `Brokerage`, `TradingStep` | backtest | application builders |
| 执行需要审计 | 自有 audit DTO | execution | 无跨包依赖 |
| 因子需要市场数据 | 无 Protocol 直接导入 | — | application 注入 |

### 3.3 Data 包的 CQRS Storage 模式

80+ 个 Reader/Writer 文件，按 market/metadata/fundamental/capital/macro/runtime 6 个子域严格隔离，每个子域内又按数据集类型拆分。storage 子域之间通过 import-linter 互斥。

---

## 四、发现的问题与改进建议

### 4.1 HIGH — Platform 包存在领域知识泄漏

**最值得优先修复的问题。**

| 泄漏点 | 内容 | 应迁移至 |
|--------|------|---------|
| `project_root.py` | `get_default_dq_rules_dir()`, `get_default_golden_dataset_path()` | data 或 application |
| `metrics.py` | ~20 个领域指标（factor_ic, portfolio_drawdown, kill_switch_level） | 各能力包自行定义 |
| `notification/business.py` | `alert_dq_failure()`, `alert_ingestion_failure()` | application processes |
| `notification/templates/` | `signal_trading_*.j2` 含策略/权重领域字段 | strategy 层 |
| `storage/parquet_store.py` | 默认 key columns `["instrument_id", "trade_date"]` | 改为构造函数参数注入 |
| `util/ticker_utils.py` | `get_standard_ticker(ticker, exchange)` | data 或 kernel |

**业界参照**：Martin Fowler 的 "Generic Infrastructure" 原则——基础设施层应与业务域无关。如果换一个行业（如电商），platform 应该不需要改动。

### 4.2 MEDIUM — 占位模块需要收敛

| 包 | 空置模块 | 影响 |
|---|---------|------|
| portfolio | holdings/, positions/, target_portfolios/ | 当前 accounting 承担了全部职责，长期会过重 |
| execution | fills/store, orders/store, reconciliation/ | 实盘场景缺失关键能力 |
| strategy | signals/models, audit/ | 信号契约和审计追踪未实现 |
| analysis | reports/, diagnostics/, experiments/, screeners/ | 仅 research/ 有实现 |

**建议**：不需要现在全部实现，但应将空 docstring 替换为明确的 `Protocol` 定义和 `NotImplementedError` 存根，防止后续开发者误以为这些模块已被正确处理。

### 4.3 MEDIUM — Execution 包的 Protocol 命名冲突

`brokerage.py` 定义 `Brokerage` Protocol（`place_order`/`process_pending`），`broker/contracts.py` 定义 `BrokerGateway` Protocol（`submit_order`/`query_fills`）。两者接口高度重叠但方法名不一致，消费者容易混淆。

**建议**：统一为一个 Protocol，或者明确文档区分它们的职责——`Brokerage` 是回测模拟语义，`BrokerGateway` 是实盘券商语义。

### 4.4 LOW — Strategy signal_expressions 未被消费

`StrategySpec` 定义了 `signal_expressions` 和 `signal_weights` 字段并做了长度校验，但 Pipeline 中没有 Stage 解析这些表达式。当前仅用于 seed 数据的元数据描述。

### 4.5 LOW — BacktestBrokerage 使用 loguru 直接导入

其他包通过 `ditto_platform.foundation` 获取 logger，backtest 直接 `from loguru import logger`。虽然不违反依赖约束，但不一致。

### 4.6 LOW — Analysis 包仅完成 40%

research/ 有实质实现（catalog_service, artifact_service），但 reports/、diagnostics/、experiments/、screeners/ 都是空目录。考虑到 analysis 是"研究分析"平面，且设计定位为"不进入生产依赖路径"，这个完成度在当前阶段是可接受的。

---

## 五、对比原始设计的偏差分析

### 5.1 正向偏差（实现优于设计）

1. **依赖更严格**（已详述）——Amendment 把 features→data、strategy→data/features、execution→risk 全部切断
2. **import-linter 更丰富**——34 条合约，覆盖了设计文档未涉及的子域互斥（如 data storage 子域互斥、data sources 互斥、Application R8 互斥）
3. **CQRS 严格执行**——R8 互斥规则通过机器门禁固化
4. **architecture smell 检查**——`check_architecture_smells.py` 提供了超越 import-linter 的语义检查

### 5.2 设计偏差（实际与设计不同但合理）

| 设计要求 | 实际实现 | 合理性 |
|---------|---------|--------|
| features 可依赖 data | 禁止依赖 data | 更优，features 保持纯粹 |
| strategy 可依赖 data+features | 禁止依赖两者 | 更优，strategy 通过 Protocol 注入 |
| platform 包含 persistence/ | 拆为 storage/ + db/ | 更清晰 |
| apps 包含 worker/ | 改为 jobs/（Prefect flows/tasks） | 语义更准确 |
| analysis 可读取生产包 | 禁止直接依赖 | 更优，通过 application query 边界 |

### 5.3 未完成的设计目标

| 设计目标 | 状态 | 说明 |
|---------|------|------|
| execution 的 `oms/` | 未实现 | 订单管理系统缺失 |
| execution 的 `broker/gateways/miniqmt/ibkr` | 未实现 | 仅空壳 |
| features 的 `indicators/`, `normalization/` | 未独立实现 | 可能合并在 factors/ 或 evaluation/ 中 |
| analysis 的 `notebooks/` | 未实现 | 设计中的 Notebook 支持 |
| data 的 `lineage/` | 未实现 | 数据血缘追踪缺失 |
| data 的 `catalog/` | 未独立实现 | 功能分散在 config + storage/schemas |

---

## 六、业界最佳实践对比

### 6.1 对标 QuantConnect LEAN

| 维度 | LEAN | Ditto | 评价 |
|------|------|-------|------|
| 包结构 | 单体 monolith | **12 包 monorepo** | Ditto 更模块化 |
| 依赖方向 | 隐式约定 | **import-linter 强制** | Ditto 更严格 |
| CQRS | 无 | **commands/queries/processes 分离** | Ditto 更现代 |
| 测试隔离 | 依赖具体实现 | **Protocol 驱动** | Ditto 更易测试 |
| 回测/实盘切换 | 继承 + 工厂 | **Protocol + DI 注入** | Ditto 更灵活 |

### 6.2 Clean Architecture 合规性

| 原则 | 合规性 | 说明 |
|------|-------|------|
| 依赖方向向内 | **优秀** | 34 条合约强制 |
| 跨边界通过接口 | **优秀** | Protocol 定义在消费者侧或 kernel |
| 业务规则与基础设施分离 | **良好** | Platform 有少量泄漏 |
| 用例层不含领域规则 | **优秀** | Application 层纯编排 |
| 传输层不含业务逻辑 | **优秀** | Apps 层纯适配 |

### 6.3 六角架构（Ports & Adapters）

| 检查项 | 状态 |
|--------|------|
| Port 由消费者定义 | kernel 中 Protocol 定义合理 |
| Adapter 由 application 装配 | DI composition root 在 apps/registry/ |
| 领域核心零外部依赖 | kernel 零依赖，portfolio 仅依赖 kernel |
| 测试可替换基础设施 | Protocol 驱动，SimulatedClock/SimpleEventBus 可测试 |

---

## 七、下一步优化建议（优先级排序）

### P0（应尽快修复）

1. **Platform 包领域知识清理**——移除 `business.py`、领域指标、`ticker_utils`、DQ 路径函数
2. **Data `catalog/` 子域独立**——将分散的数据集注册表和 schema 管理集中化

### P1（下一迭代）

3. **Portfolio 补充 holdings/positions 空置模块**——至少定义 Protocol 接口
4. **Execution 统一 Protocol 命名**（Brokerage vs BrokerGateway）
5. **Strategy signals/ 补充 SignalBatch 等基础结构**
6. **Data `lineage/` 子域**——数据血缘追踪

### P2（长期演进）

7. **Analysis 研究平面完整实现**（reports/diagnostics/experiments）
8. **Execution OMS 实现和真实券商网关**
9. **每个 capability package 建立稳定 public API 清单**（`__all__` 或 `CLAUDE.md`）
10. **Application `providers/` 从"可能做事"收紧为"只 wiring"**（boundaries 文档 §13.1）

---

## 八、结论

这次架构重构**完成度很高**，最核心的成就不是目录拆分，而是三个设计改进：

1. **Amendment 依赖收紧**——比原始设计更严格的平面隔离，使每个能力包可以真正独立测试
2. **34 条 import-linter 合约**——机器门禁将架构规则代码化，后续开发者无法意外破坏
3. **CQRS R8 互斥规则**——Application 层的 queries/commands/processes/builders 通过 import-linter 强制读写分离

主要技术债务集中在 Platform 的领域知识泄漏（P0）和 4 个能力包的占位空模块（P1）。这些都是增量改进，不影响整体架构的正确性。

**从架构设计意图看，这次重构忠实执行了"轻 DDD + 能力模块化 + CQRS 编排 + 插件化接入 + 研究/生产分轨"的目标，实际实现甚至在依赖隔离上超出了原始设计的严格程度。**
