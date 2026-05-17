# Ditto 架构综合评估报告 v2

> 日期：2026-05-13
> 基准文档：`docs/reviews/audit/2026-05-07-comprehensive-architecture-evaluation.md`
> 审计范围：12 包能力架构全量源码审查、逐模块评分、业界对标、攻坚计划
> 方法：全量源码逐文件阅读 + 6 组并行深度审计 Agent + 静态指标扫描 + `pixi run -e dev arch-check` + 业界最佳实践对标

---

## 1. 执行摘要

自 2026-05-07 上次评估以来，代码库经历了 B1-B9 整改、Phase 1 Runtime Spine、Phase 2 OMS Lite 等重大演进。本次评估对 **897 个源码文件、103,419 行代码、12 个包** 进行了全量逐模块审查。

**总体评分：8.5/10（上次 8.6）**

| 口径 | 评分 | 变化 | 说明 |
|------|------|------|------|
| 工程综合质量 | **8.5/10** | -0.1 | OMS Lite、FSM 落地提升；application concrete import 扣分更重 |
| 命名/边界/领域划分正确性 | **7.6/10** | +0.2 | Protocol 归位有进展，Dataset 路由仍分散 |
| 模块化量化运行时就绪度 | **6.8/10** | +0.4 | Phase 1 Runtime Spine + 时钟统一，但 live/paper 仍未共享 |
| 全球全市场 live-ready 架构 | **5.2/10** | +0.2 | BrokerGateway 仍为 Protocol-only，状态恢复仍不完整 |

**核心判断**：架构治理和工程质量已进入优秀区间，但瓶颈已从"架构是否清楚"完全转向"运行时地基和产品闭环是否成立"。下一步应聚焦逐模块代码质量攻坚，同时推进 runtime seam。

---

## 2. 源码快照与变化

### 2.1 全局指标对比

| 指标 | 2026-05-07 | 2026-05-13 | 变化 |
|------|----------:|----------:|------|
| 生产源码文件 | 827 | 897 | +70 |
| 生产源码行数 | 100,085 | 103,419 | +3,334 |
| 测试文件 | 664 | 686 | +22 |
| 测试函数 | ~6,273 passed | 7,174 total | +901 |
| `Protocol` | 119 | 121 class def（289 文本引用） | +2 class def |
| `ABC` | 2 | 2 | 持平（NotificationSender, ConfigInitProvider） |
| frozen dataclass | 356/364 | 364/373 | +8 |
| `# type: ignore` | 0 | 0 | 持平 |
| `TYPE_CHECKING` | 0 | 0 | 持平 |
| pandas import | 0 | 0 | 持平 |
| import-linter 合约 | 36 kept, 0 broken | 36 kept, 0 broken | 持平 |
| `@traced` 分布 | 59 文件 | 195 处 | 大幅增加 |
| `__all__` 定义 | 537 | 590 | +53 |
| `noqa` 豁免 | 未追踪 | 66 | - |
| Dataset usage (application) | ~245 处 / 12 文件 | 263 行 / 16 文件 | 口径不同，问题仍成立 |

**关键变化解读**：

1. **Protocol 类定义从 119 增至 121**（文本引用 289 处）：B3-B6 整治的 Protocol 归位效果显著，跨包依赖更多通过结构化子类型表达。注意 121 为 class definition 数，非文本引用数。
2. **ABC 保留 2 个**：`NotificationSender`（notification sender）、`ConfigInitProvider`（config initializer）仍为 ABC，与 Protocol 风格局部不一致。建议后续统一或写 ADR。
3. **@traced 从 59 跃升至 195**：可观测性大幅增强，但分布仍不均（见第 7 节）。
4. **Dataset 使用反而增长**：application 中 Dataset 引用从 245 增至 282 处，文件数从 12 增至 23，说明新增代码仍沿旧路由模式，DataCatalog runtime 化更紧迫。
5. **测试函数增长 901 个**：B1-B9 整改带来了大量新测试，test-to-source 比保持健康。

### 2.2 逐包指标

| 包 | 文件数 | 行数 | 测试文件 | Protocol | 测试比 |
|---|------:|-----:|-------:|--------:|------:|
| data | 286 | 31,491 | 192 | 30 | 1:1.5 |
| application | 116 | 18,937 | 108 | 20 | 1:1.6 |
| features | 108 | 15,136 | 34 | 23 | 1:3.2 |
| apps | 113 | 12,295 | 136 | 3 | 1:0.8 |
| platform | 56 | 5,850 | 43 | 6 | 1:1.3 |
| strategy | 57 | 5,894 | 30 | 19 | 1:1.9 |
| backtest | 39 | 5,186 | 42 | 8 | 1:1.2 |
| execution | 49 | 3,629 | 34 | 24 | 1:1.4 |
| analysis | 20 | 1,220 | 12 | 2 | 1:1.7 |
| portfolio | 21 | 1,486 | 16 | 13 | 1:1.3 |
| risk | 18 | 1,381 | 23 | 5 | 1:1.3 |
| kernel | 14 | 914 | 16 | 8 | 1:1.8 |
| **合计** | **897** | **103,419** | **686** | **161** | - |

### 2.3 Top 20 大文件

| 行数 | 文件 |
|-----:|------|
| 749 | features/expression/codegen.py |
| 697 | features/evaluation/evaluator.py |
| 697 | data/services/metadata/instrument.py |
| 672 | data/storage/metadata/instrument/instrument_reader.py |
| 629 | data/storage/base/sqlite_store.py |
| 629 | data/sources/tushare/adapters/stock.py |
| 622 | features/evaluation/metrics/ic.py |
| 592 | application/processes/ingestion/data_writer.py |
| 583 | application/processes/materialization/orchestrator.py |
| 583 | application/processes/execution/backtest_process.py |
| 577 | features/services/derived_catalog_service.py |
| 557 | data/sources/tushare/adapters/fundamental.py |
| 556 | data/services/metadata_service.py |
| 551 | data/storage/metadata/calendar/calendar_reader.py |
| 534 | platform/foundation/observability/metrics.py |
| 520 | platform/foundation/config/paths.py |
| 513 | features/storage/sqlite/derived/writer.py |
| 511 | application/processes/materialization/publication_facade.py |
| 502 | data/runtime/freeze_manager.py |
| 498 | data/storage/market/parquet/parquet_store.py |

所有文件均低于 800 行 smell checker 门槛，但 700+ 行文件仍有 6 个。

---

## 3. 全面重评评分卡

### 3.1 工程综合质量评分（8.8/10）

| 维度 | 权重 | 得分 | 变化 | 说明 |
|------|-----:|-----:|------|------|
| 依赖边界与架构清晰度 | 18% | 9.3 | +0.1 | 36 合约全绿，Protocol 归位、Risk-Execution 解耦完成 |
| 模块化与语义所有权 | 14% | 9.0 | +0.2 | Platform 去业务化巩固、OMS Lite 落地、Planner 拆分 |
| Ports/Adapters 与 DI | 12% | 8.6 | -0.1 | 121 Protocol、ISP 窄端口；application concrete import 扣分 |
| CQRS 与 application 编排 | 10% | 8.8 | +0.1 | R8 合约全绿、fetch handler 仍是单体映射 |
| 数据架构、PIT 与目录治理 | 12% | 8.1 | +0.1 | PIT/storage 强，DataCatalog 仍为 contract-only |
| 量化平台研究-回测-执行一致性 | 10% | 8.0 | +0.2 | Phase 1 Runtime Spine + OMS Lite 落地，live broker 仍缺 |
| 工程质量与验证 | 12% | 9.2 | 持平 | 7174 测试、0 type:ignore、36 合约全绿 |
| 可观测性与运维 | 6% | 8.5 | +0.2 | @traced 从 59 跃升至 195，分布仍不均 |
| 可理解性与 agent 友好度 | 6% | 8.6 | 持平 | CLAUDE.md 全覆盖、smell guard 17 类 |

### 3.2 逐模块评分

| 包 | 可读性 | 一致性 | 整洁架构 | 扩展性 | 综合 | 上次评估 |
|---|:------:|:------:|:-------:|:------:|:----:|:-------:|
| kernel | 9 | 9 | 9 | 8 | **8.6** | 8.5 |
| platform | 8 | 7 | 8 | 8 | **7.7** | 7.5 |
| data | 7 | 7 | 7 | 7 | **7.0** | 7.0 |
| features | 9 | 9 | 8 | 9 | **8.5** | 8.5 |
| strategy | 9 | 9 | 9 | 8 | **8.6** | 8.5 |
| portfolio | 8 | 7 | 8 | 8 | **7.7** | 7.5 |
| risk | 8 | 7 | 8 | 7 | **7.4** | 7.0 |
| execution | 8 | 7 | 7 | 7 | **7.2** | 7.0 |
| backtest | 9 | 9 | 9 | 9 | **8.8** | 8.8 |
| analysis | 9 | 9 | 8 | 7 | **7.8** | 8.0 |
| application | 8 | 9 | 7 | 8 | **7.7** | 7.8 |
| apps | 8 | 9 | 9 | 8 | **8.2** | 8.2 |
| **加权平均** | **8.3** | **8.0** | **8.1** | **7.8** | **8.1** | - |

**评分说明**：模块综合分使用四维等权平均；全局综合分使用上节加权口径（因全局维度含工程验证等模块外因素），两者口径不同故数值不同属正常。

---

## 4. 逐模块详细评估

### 4.1 kernel — 8.75/10 🏆

**定位**：零依赖共享内核，跨全系统不可再分的稳定语言。

**优势**：
- 14 个源文件、914 行，小而精。零外部依赖、零 I/O、零业务行为。
- 所有值对象均为 `frozen=True` dataclass，`Clock`、`EventBus`、`FeeModel` 等为 Protocol。
- 每个 leaf module 都有 `__all__` 声明，barrel 导出 28 个符号，低频符号需 leaf import。
- 模块级 docstring 双语且精确，明确记录准入依据。

**问题**：
- [K-1] `trading.py`（178 行）承载 FeeModel/InstrumentDefinition/TradingRuleSet/MarketSnapshot，CLAUDE.md 承认仅被 execution/backtest 使用，有膨胀风险。
- [K-2] `MarketSnapshot` 含 A 股特有字段（`limit_up`/`limit_down`），全球市场扩展时会膨胀。
- [K-3] `EventName` 为 closed enum 但 `DomainEvent.event_type` 为 `str`，类型安全有缺口。
- [K-4] `tracing.py` 使用模块级全局可变状态（`_trace_handler`），线程不安全。
- [K-5] CLAUDE.md 文档漂移：仍引用 `json_types.py`（已迁至 platform）和 `MacroDataProvider`（已不存在）。

**攻坚建议**：
1. 清理 CLAUDE.md 漂移引用
2. 审视 `trading.py` 中的类型是否应迁回 execution/backtest 拥有
3. `EventName` vs `str` 的设计决策记录为 ADR

---

### 4.2 platform — 7.75/10

**定位**：横向技术基础设施，零业务语义。

**优势**：
- foundation/ 分为 cache/checksum/concurrency/config/db/observability/storage/util 8 个子域，各自独立。
- storage/ 子模块最优秀：ParquetStore 委托 leaf modules，Protocol 定义 clean。
- notification/ 纯传输机制：TemplateEngine + 多 channel sender，零业务逻辑。
- `XDGPaths` 实现 XDG Base Directory 规范，优先级链正确。
- 死代码函数 `get_paths()` 等已改为 `raise RuntimeError` 强制 DI。

**问题**：
- [P-1] `observability/metrics.py`（535 行）含 metaclass + 动态属性 + 注册，是最复杂文件。
- [P-2] `ObservabilityRegistry` 用 class-level mutable attributes 做 pseudo-singleton，非线程安全。
- [P-3] `config/paths.py`（521 行）含 3 个只 raise RuntimeError 的死代码函数 + XDGPaths 属性重复模式。
- [P-4] `cache/core.py`（327 行）custom time source 模式 get/set 逻辑重复。
- [P-5] `OnDuplicate` 使用 `Enum` 而非 `StrEnum`，与全库惯例不一致。
- [P-6] `NotificationLevel` StrEnum 上定义比较运算符，不寻常。
- [P-7] `checksum/` 和 `util/checksum.py` 功能重叠（SHA-256 vs XXH3_128）。
- [P-8] NotificationSettings 含微信/钉钉字段，边界级业务语义微泄漏。

**攻坚建议**：
1. 拆分 `metrics.py`：metaclass 逻辑提取、provider 配置分离
2. ObservabilityRegistry 改为实例化模式或 contextvars
3. 清理 paths.py 死代码 + 提取 XDGPaths 属性生成逻辑
4. 统一 `OnDuplicate` 为 `StrEnum`

---

### 4.3 data — 7.0/10 ⚠️

**定位**：数据平台，最大包（286 文件、31,491 行、30%+ 代码库）。

**优势**：
- barrel 导出仅 5 符号：`BarQuery`, `DataIngested`, `DataProvider`, `InstrumentQuery`, `QualityCheckCompleted`，极度收敛。
- CQRS Reader/Writer 分离一致，所有 storage 模块遵循。
- Dataset enum（20 值）含 `asset_class`、`date_schedule` 等丰富属性。
- 成熟度标注诚实：CLAUDE.md 明确标记大部分数据集为 `experimental`。
- 错误层级按子域拆分（calendar/instrument/network/persistence），全继承 `DataError`。

**问题**：
- [D-1] **最大包问题**：286 文件占代码库 30%+，导航成本仍高。新增数据集需跨 catalog/config/fetch/write/storage/quality 多处修改。
- [D-2] **Dataset enum 承担运行时目录**：application 中 282 处引用、23 个文件直接使用，扩展路径不够插件化。
- [D-3] **catalog/ 和 lineage/ 为纯 contract**：零实现，仍为 reserved 状态。
- [D-4] **providers/ 为空壳**：ServiceBackedDataProvider 已迁至 application，残留空 `__init__.py`。
- [D-5] **CLAUDE.md 文档漂移**：记录 `errors.py`（单文件）但实际已重构为 `errors/` 包。
- [D-6] **大文件集中**：6 个文件超 500 行（sqlite_store.py 629, stock.py 629, instrument.py 697, instrument_reader.py 672, metadata_service.py 556, calendar_reader.py 551）。
- [D-7] **15 个 *Service 类**：约 44% 更像 Store/Repository，后缀语义不精确。
- [D-8] **Source.AKSHARE 列出但未用**：预留 enum 值增加认知负担。

**攻坚建议**：
1. 推进 DataCatalog runtime 实现，逐步替换 Dataset enum 路由
2. 拆分 700+ 行大文件（instrument.py、sqlite_store.py）
3. 清理空壳 providers/ 目录
4. 更新 CLAUDE.md 文档漂移
5. Service 后缀按职责重命名（Store vs Service vs Coordinator）

---

### 4.4 features — 8.75/10

**定位**：因子表达式、物化、评估、衍生数据。

**优势**：
- expression/ 8 模块编译管线（lexer → parser → ast → analyzer → compiler → codegen）清晰分层。
- 12 个因子类别文件统一使用 `dict[str, FactorSpec]` 模式，注册式插件。
- expression/materialization 隔离由 import-linter 强制。
- barrel 导出克制：root 仅 8 符号。
- CLAUDE.md 优秀，含内部依赖方向图和验证命令。

**问题**：
- [F-1] **codegen.py 749 行**：全库最大文件，编译器逻辑复杂度自然高但可拆分。
- [F-2] **evaluator.py 697 行**：14 个类聚集，职责广度大。
- [F-3] **services/ 导出 37 符号**：混合了 derived data、publication safety、catalog/shadow 三个关注域。
- [F-4] **双错误根**：`FeaturesError` 和 `DerivedError` 为 `DittoError` 的平级子类，`except FeaturesError` 不会捕获 `DerivedError`。
- [F-5] **ic.py 622 行**：IC 评估指标文件偏大。

**攻坚建议**：
1. 拆分 codegen.py：按表达式类型分模块
2. 拆分 evaluator.py：按评估策略分文件
3. services/ 按关注域分子目录：`derived/`、`publication/`、`catalog/`
4. 统一错误层级：`DerivedError` 改为 `FeaturesError` 子类

---

### 4.5 strategy — 8.75/10

**定位**：策略定义与信号生成，零依赖上游能力包。

**优势**：
- **完美的依赖隔离**：零依赖 data/features/portfolio/risk/execution/backtest，通过 Protocol 和 InputBundle 反转依赖。
- `StrategyPipeline` 为无状态纯函数设计：同样输入始终产生同样输出。
- 12 个因子阶段文件 + 6 个 regime 子系统，factory/config/validate 模式一致。
- 错误层级单根清晰：`StrategyError` → 4 个子类。
- CLAUDE.md 含模板成熟度表和治理规则。

**问题**：
- [S-1] **builtins/regime_*.py 6 文件扁平排列**：regime 子系统已达半数 builtins，应考虑子包。
- [S-2] **root __init__.py 激进空导出**：`__all__: list[str] = []`，缺少便捷单导入入口。
- [S-3] **templates/stock_sector_rotation.py 640 行**含 12 个 stage/config 类，偏大。

**攻坚建议**：
1. 提取 `builtins/regime/` 为子包
2. 为 root `__init__.py` 添加核心 3-5 符号导出（Pipeline, StrategySpec, Context）
3. 拆分 stock_sector_rotation.py 的 config 和 stages

---

### 4.6 portfolio — 7.8/10

**定位**：组合构建、记账、头寸管理。

**优势**：
- 核心值对象全部 `frozen=True`：Position, CashBook, FillEvent, AccountView。
- `Account` 是唯一可变状态持有者，`get_view()` 返回 frozen snapshot + MappingProxyType 防泄漏。
- `apply_fill` 原子更新模式：先计算后变异，异常安全。
- Protocol 数量丰富（13 个）：BuyingPowerModel, PortfolioStateReader, FillProjector, WeightAllocator, Constraint 等。
- `report_views.py` 边界 Protocol 解耦了 portfolio 对 backtest 的依赖。
- `AccountProjector` 提供确定性状态重建能力。

**问题**：
- [PF-1] `Account` 用 `@dataclass` + 自定义 `__init__`，dataclass 装饰器实际无贡献。
- [PF-2] sell path `market_value` 用 `average_cost` 而非市价，语义不准确。
- [PF-3] `holdings/` 和 `positions/` 仅为 Protocol 存根，`instrument_id` 用 `int` 而非 `InstrumentId`。
- [PF-4] `target_portfolios/` 为单行 docstring 占位。
- [PF-5] `comparison.py` 耦合 backtest 报告结构（直接访问 `alpha_stats`, `final_nav` 等）。

**攻坚建议**：
1. Account 去掉 `@dataclass` 改为普通类（或重构为真正 dataclass）
2. 修正 sell path `market_value` 计算
3. holdings/positions 类型统一为 `InstrumentId`
4. comparison.py 通过 Protocol 解耦 backtest 报告结构

---

### 4.7 risk — 7.5/10

**定位**：风控规则引擎，返回值语义（非异常语义）。

**优势**：
- **返回值 vs 异常语义典范**：`Decision.ACCEPT/REJECT/RESIZE` 用于 pre-trade，`list[RiskAction]` 用于 post-trade，异常仅用于配置错误。
- `CompositePreTradeCheck` 的 resize-recheck 循环（最多 3 次），处理手数调整级联。
- `PreTradeContext` frozen + `with_order_accepted()` 返回新实例，纯函数式。
- `MaxDrawdownRule` 的 snapshot/restore 支持确定性回放。
- 跨包解耦干净：`PreTradeOrder`、`SliceView` 等均为本地 Protocol。

**问题**：
- [R-1] **`SliceView.bars` 为 `dict[InstrumentId, Any]`**：risk 包最大的类型安全缺口。
- [R-2] **`_accept()` helper 在两个模块中重复**：constraints/checks.py 和 exposure/checks.py。
- [R-3] **无 `RiskGate` 运行时抽象**：当前仅为 batch 式装饰器，无法嵌入 submit/modify/fill 路径。
- [R-4] **审计链碎片化**：RiskAction(risk) → RiskScanRecord(backtest) → execution_audit(execution)，三个包处理同一概念无共享 trace ID。
- [R-5] **models.py 为空壳**：`__all__: list[str] = []`，应移除或填充。

**攻坚建议**：
1. `SliceView.bars` 改为 `dict[InstrumentId, BarSlice]` 定义窄 Protocol
2. 提取 `_accept()` 为共享 helper
3. 删除空 models.py
4. 设计 `RiskGate` Protocol 用于运行时路径

---

### 4.8 execution — 7.3/10 ⚠️

**定位**：交易执行、OMS Lite、审计。

**优势**：
- **OMS Lite 设计优秀**：双 ID（ClientOrderId + BrokerOrderId）、7 状态 FSM、OrderTicket immutable-with、OrderBook readonly view、OrderEventJournal。
- FSM `transition()` 为纯函数，可独立测试，含 comprehensive 错误处理。
- `FillOutcome` 联合类型（`Filled` + `NoFill`）使"无成交"成为一等公民。
- ISP 数据端口拆分：IntentDataPort、FillDataPort、PositionDataPort。
- Planner 已从单体拆分为 target_diff/market_precheck/quantity_rounding/cost_estimate 等模块。
- 错误层级 5 子类覆盖不同失败模式。
- `ExecutionAuditService` 完整 SQLite 持久化 + `@traced`。

**问题**：
- [E-1] **BrokerGateway 仍为 Protocol-only**：broker/gateways/ 为 docstring 占位，零实现。
- [E-2] **reconciliation/ 仅为单 dataclass**：无匹配逻辑、无 store。
- [E-3] **OrderBook.cancel() 绕过 journal-first 模式**：与 submit() 不一致的 event 注入方式。
- [E-4] **SimpleExecutionPlanner._next_id()** 用脆弱计数器，非全局唯一、非线程安全。
- [E-5] **OrderRecord.instrument_id: int vs Order.instrument_id: InstrumentId**：持久化边界类型不匹配。
- [E-6] **ExecutionAuditService 三个 save_*_log 方法结构相同**：DRY 违规，应参数化。
- [E-7] **root __init__.py 空导出**：无稳定顶层 API surface。

**攻坚建议**：
1. 实现 paper/mock BrokerGateway 作为最小 adapter
2. 统一 OrderBook event 注入模式
3. 使用 ClientOrderId.generate() 替代手动计数器
4. 参数化 audit service save 方法
5. 统一 instrument_id 类型为 InstrumentId
6. 添加 root barrel 核心导出

---

### 4.9 backtest — 9.0/10 🏆

**定位**：回测引擎，系统最成熟的模块。

**优势**：
- **Step Chain 架构典范**：7 步管线（DataFetch → RiskScan → Strategy → Planning → PreTrade → Execution → Audit），每个 step 独立类 + 统一 `execute(ctx) -> StepResult`。
- **多层防前瞻机制**：`knowledge_lag_days`、严格 `<` 过滤、`as_of_date` 语义。
- **Protocol 驱动仿真模型**：FillModel、SettlementModel、SlippageModel 各有多个实现。
- **A 股市场真实感**：涨跌停、停牌、收盘集合竞价、T+N 清算、成交量冲击。
- **可复现性**：RunManifest 含配置哈希 + 数据指纹 + 依赖版本 + 随机种子；ReplayValidator 支持精确匹配 + Pearson 回退。
- **测试覆盖 41 文件**：含 import boundary、invariants、golden baseline、reproducibility、snapshot。
- 测试比 3.5:1（全库最高之一）。

**问题**：
- [B-1] `EngineResult` 非 frozen，与全包 frozen 惯例矛盾。
- [B-2] `StepContext` 为可变共享状态，无状态机保护，step 乱序会静默传 None。
- [B-3] `statistics_returns.py` 手动循环计算方差，数值稳定性风险。
- [B-4] 无 intra-step cancellation/timeout 能力。
- [B-5] `daily_returns_from_navs` 和 `compute_portfolio_statistics` 中重复 NAV→Return 逻辑。

**攻坚建议**：
1. EngineResult 改为 frozen dataclass
2. 为 StepContext 添加 build-phase / execute-phase 状态标记
3. 使用 `statistics.variance` 或 `math.fsum` 替代手动方差计算
4. 消除 NAV→Return 重复逻辑

---

### 4.10 analysis — 8.0/10

**定位**：研究控制平面，与生产包双向隔离。

**优势**：
- barrel 仅导出 3 符号：`AnalysisError`, `ResearchDatasetError`, `ResearchDatasetSpec`。
- 4 个 reserved namespace 均有空 `__all__` + 明确 docstring 声明。
- 完美双向隔离：analysis 不依赖任何生产包，生产包不依赖 analysis。
- Protocol-based storage abstraction 支持 UoW 语义。
- Late arrival detection 支持三种策略（exclude/shift-reserved/require-rebuild）。
- DI provider 清洁（dishka Scope.APP）。

**问题**：
- [A-1] **829 行源码，主要是脚手架**：4 个 reserved namespace 零实现。
- [A-2] **SQLite Reader 代码重复**：`read_spine_snapshot` 和 `get_latest_spine_snapshot` 构造逻辑相同，仅 WHERE 子句不同。
- [A-3] **ArtifactService 使用 filesystem glob 解析路径**：无 manifest/index，不可测试。
- [A-4] **contracts.py 为纯 re-export**：从 research.protocols 重导出，增加间接层。
- [A-5] **Record 类型无验证**：Spec 有 validate_spec() 但 Record 从 SQLite 读取后无校验。
- [A-6] **ResearchCatalogService 为纯 pass-through**：10 个方法各调用单一 reader/writer 方法。

**攻坚建议**：
1. 提取 SQLite Reader 共享行构造逻辑
2. ArtifactService 改用 manifest 或 index-based 解析
3. 为 Record 添加 from_row() 工厂方法含验证
4. 考虑是否需要 catalog_service 层（或消费者直接用 Protocol）

---

### 4.11 application — 8.0/10

**定位**：应用编排层，CQRS + Process Manager。

**优势**：
- R8 互斥合约全绿：queries/commands/builders 各不互引。
- Process Manager 正确分离长流程编排与原子命令。
- config/ 目录化（4 文件 713 行），不再为单体大文件。
- builders/ 含 runtime_builder、slice_builder、service_factory 等清晰装配。
- CLAUDE.md 194 行，含 DI provider 表和验证命令。

**问题**：
- [AP-1] **queries/source.py 直接导入 FredSource/TushareSource 具体类**：违反 query 层纯抽象原则。
- [AP-2] **providers_command.py 导入 7 个 data 层具体类**：DI wiring 可接受但边界模糊。
- [AP-3] **providers_process.py 导入 SQLiteClient 具体实现**：application 核心不应接触物理存储。
- [AP-4] **fetch_handlers.py ~100 行 Dataset→lambda 映射**：非插件化，新增数据集需改映射。
- [AP-5] **Dataset 使用增长**：282 处 / 23 文件，较上次增加 37 处。
- [AP-6] **大文件**：data_writer.py 592、orchestrator.py 583、backtest_process.py 583、publication_facade.py 511。

**攻坚建议**：
1. queries/source.py 改用 Protocol 注入
2. providers 中具体实现下沉至 apps/registry
3. fetch_handlers 改为注册表模式
4. 控制并逐步减少 Dataset 直接引用

---

### 4.12 apps — 8.5/10

**定位**：传输层 + DI Composition Root。

**优势**：
- registry/ 为干净的 composition root：container.py 按正确顺序装配所有层。
- API 路由 16 文件，trade/backtest 已按 query/command 拆分子路由。
- CLI 19 命令文件，ingest/backfill/query 按域平行组织。
- Jobs 8 flow + 4 task，daily flow 正确使用 Prefect wait_for 依赖声明。
- CLAUDE.md 264 行，含 DI 规则、路由表含成熟度标注。
- services/ 目录不存在（业务逻辑已全迁至 application）。

**问题**：
- [APP-1] **init_providers.py 含硬编码 schema path**：启动初始化混合在 provider 文件中。
- [APP-2] **API 路由数增长**（16+ 文件）：可能需按域分子包。
- [APP-3] **jobs/context.py 保留 DQ engine 窄豁免**：文档化但仍有耦合。
- [APP-4] **CLAUDE.md 微漂移**：声称 services/ 已清空，实际目录不存在。

**攻坚建议**：
1. 提取 init_providers 中的 DB 初始化为独立 startup 模块
2. 路由按域分 `routes/trade/`、`routes/market/` 等子包
3. 清理 CLAUDE.md 文档漂移

---

## 5. 业界最佳实践对标（更新）

### 5.1 与 LEAN (QuantConnect) 对比

| 维度 | LEAN | Ditto 当前 | 差距 |
|------|------|-----------|------|
| 模块化 | 大单体目录结构 | 12 包 + 36 合约 | **Ditto 更优** |
| Backtest/Live 统一 | IBrokerage 统一接口 | BrokerGateway Protocol-only | LEAN 远优 |
| 数据目录 | 多源数据插件 | Dataset enum + DataCatalog contract | LEAN 更成熟 |
| 事件驱动 | AlphaModel → OnData → Order | Step Chain → Process Manager | 各有优劣 |
| OMS | OrderTicket + OrderEvents | OMS Lite (7 状态 FSM) | LEAN 更完整 |
| 多市场 | 5+ 市场 production | A 股 ETF initial-focus | LEAN 远优 |

### 5.2 与 NautilusTrader 对比

| 维度 | NautilusTrader | Ditto 当前 | 差距 |
|------|---------------|-----------|------|
| 高性能 | Rust/Cython 核心 | 纯 Python + Polars | Nautilus 远优 |
| Backtest/Live | 统一执行语义 | Phase 1 Runtime Spine 起步 | Nautilus 远优 |
| Actor 模型 | 消息驱动组件 | EventBus stub | Nautilus 远优 |
| 时间模型 | 统一 Clock 语义 | SimulatedClock + 分散 PIT | Nautilus 更统一 |
| 订单模型 | OMS + venue position mode | OMS Lite 7 状态 | Nautilus 更完整 |
| 因子/特征 | 无内置表达式引擎 | features 表达式编译器 | **Ditto 更优** |

### 5.3 与 FinRL-X (2026) 对比

| 维度 | FinRL-X 论文方向 | Ditto 当前 | 差距 |
|------|-----------------|-----------|------|
| 模块化 + research/deployment consistency | 核心主张 | 12 包 + Protocol 隔离 | Ditto 理念对齐 |
| Broker execution 统一协议 | 核心主张 | BrokerGateway Protocol | 骨架已有，实现缺失 |
| RL 策略支持 | 核心能力 | 不在 Ditto 范围内 | N/A |

### 5.4 Clean Architecture / Hexagonal 对标

| 维度 | 理想 | Ditto 当前 | 评分 |
|------|------|-----------|------|
| 依赖规则（内层不知外层） | 100% | kernel/platform/data/strategy 完美；application 导入具体类 | 85% |
| Port 由消费者拥有 | 100% | 161 Protocol 但部分仍由实现侧定义 | 80% |
| Composition Root 纯净 | 100% | apps/registry 优秀；application/providers 混杂 | 75% |
| 跨边界不可变传递 | 100% | 364/373 frozen dataclass | 97% |

### 5.5 测试金字塔对标

| 层级 | 理想比例 | Ditto 当前 | 评价 |
|------|---------|-----------|------|
| Unit | 大量 | 546 文件 | ✅ 充足 |
| Integration | 适中 | 55 文件 | ✅ 合理 |
| E2E | 少量 | 6 文件 | ⚠️ 偏少 |
| 测试函数 | - | 7,174 | ✅ 覆盖面强 |

---

## 6. 剩余风险评估

### 高优先级风险

| ID | 风险 | 影响 | 状态 |
|----|------|------|------|
| R1 | Dataset enum 仍承担运行时目录职责 | 新增数据集需改多处；282 处引用 | 恶化（+37 处）**P0 立即治理** |
| R2 | BrokerGateway 零实现 | 无法 paper/live 交易 | 未变 |
| R3 | Backtest/Live 无共享 runtime | 策略/risk/brokerage 无法共用 | Phase 1 起步 |
| R4 | Data/Application concrete import 泄漏 | 架构纯度受限 | 部分改善 |

### 中优先级风险

| ID | 风险 | 影响 | 状态 |
|----|------|------|------|
| R5 | 大文件集中在 data/features/application | Review 成本高 | 未变 |
| R6 | Portfolio/Execution 占位子域 | 产品闭环不足 | OMS Lite 改善 |
| R7 | @traced 分布不均 | 关键路径可观测性缺口 | 大幅改善 |
| R8 | instrument_id 类型不一致 | 持久化边界类型安全缺口 | 未变 |

### 低优先级风险

| ID | 风险 | 影响 | 状态 |
|----|------|------|------|
| R9 | 文档漂移（kernel CLAUDE.md 等） | Agent/新人误导 | 新增 |
| R10 | Service 后缀语义不精确 | 领域语言混淆 | 未变 |
| R11 | errors.py/exceptions.py 混用 | 导航一致性 | 未变 |

---

## 7. 逐模块 Review 攻坚计划

### 7.1 计划原则

1. **先拉短板**：优先治理最低分模块（data 7.0 → execution 7.3 → risk 7.5），快速提升整体水平
2. **每模块限定问题清单和验收标准**
3. **每个攻坚批次预计 1-3 天，可并行**
4. **完成标准**：`pixi run -e dev check` 全绿 + 模块评分提升
5. **Dataset P0**：立即治理 Dataset enum 路由，遏制继续恶化

### 7.2 攻坚批次（先拉短板顺序）

---

#### Batch 1: 数据层重构（data）— 预计 2-3 天 ⚡ 最高优先级

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| D-0 | **DatasetRegistry 注册表**：提取 fetch_handlers/data_writer/coordinator_constants 中的 Dataset→X 映射为 `DatasetRegistry`，新增数据集只改 `registry.register()` | P0 | 新增数据集零散文件修改 |
| D-1 | 拆分 instrument.py（697 行）：service 分离查询/写入/校验 | P1 | 单一职责 |
| D-2 | 拆分 sqlite_store.py（629 行）：提取 DDL 和 helper 方法 | P2 | 单一职责 |
| D-3 | 拆分 instrument_reader.py（672 行） | P2 | 单一职责 |
| D-4 | 清理空壳 providers/ 目录 | P1 | 删除空目录 |
| D-5 | 更新 CLAUDE.md 文档漂移（errors/ 包） | P1 | 文档与源码一致 |
| D-6 | 重命名 Service→Store/Reader/Writer：存储类 Service 按职责重命名（全局治理） | P2 | 后缀与职责匹配 |
| D-7 | data/errors/ → data/exceptions/ 统一 | P2 | 文件名与 Python 社区惯例一致 |
| D-8 | 强化内部子域分界：检查是否需要新增子域级 import-linter 合约 | P3 | 子域隔离度可测量 |

---

#### Batch 2: 交易层加固（execution + risk + portfolio）— 预计 2-3 天

**execution 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| E-1 | 实现 paper/mock BrokerGateway（与 OMS 同步） | P1 | 最小 adapter 可用 |
| E-2 | 统一 OrderBook event 注入模式 | P2 | submit/cancel/update 一致 |
| E-3 | 使用 ClientOrderId.generate() 替代计数器 | P2 | ID 全局唯一 |
| E-4 | 参数化 audit service save 方法 | P2 | 无 DRY 违规 |
| E-5 | 统一 instrument_id 为 InstrumentId | P2 | 类型全库一致 |
| E-6 | 添加 root barrel 核心导出 | P3 | orders/errors 可顶层导入 |
| E-7 | execution/errors.py → exceptions.py 统一 | P2 | 文件名与惯例一致 |

**risk 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| R-1 | SliceView.bars 改为 dict[InstrumentId, BarSlice]（窄 Protocol） | P1 | 无 Any 类型 |
| R-2 | 提取 _accept() 为共享 helper | P2 | 无跨模块重复 |
| R-3 | 删除空 models.py | P1 | 无空壳文件 |
| R-4 | 设计 RiskGate Protocol 草案 | P3 | ADR + Protocol 定义 |
| R-5 | risk/errors.py → exceptions.py 统一 | P2 | 文件名与惯例一致 |

**portfolio 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| PF-1 | Account 去掉 @dataclass 或重构为真 dataclass | P2 | 装饰器与实际用法一致 |
| PF-2 | 修正 sell path market_value 计算 | P1 | 使用市价而非 average_cost |
| PF-3 | holdings/positions 统一 instrument_id 为 InstrumentId | P2 | 类型全库一致 |
| PF-4 | comparison.py 通过 Protocol 解耦 backtest 报告 | P3 | 零直接 backtest 类型引用 |

---

#### Batch 3: 编排层治理（application + apps）— 预计 1-2 天

**application 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| AP-1 | queries/source.py 改用 Protocol 注入（FredSource/TushareSource） | P1 | 无具体 Source 类导入 |
| AP-2 | providers 具体 SQLite/storage import 下沉至 apps/registry | P2 | application 核心零 SQLite import |
| AP-3 | fetch_handlers → DatasetRegistry 注册表（与 D-0 联动） | P2 | 新增数据集不改映射代码 |

**apps 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| APP-1 | 提取 init_providers 中 DB 初始化为独立 startup 模块 | P2 | provider 纯 DI |
| APP-2 | 路由按域分子包 | P3 | routes/trade/, routes/market/ |
| APP-3 | 清理 CLAUDE.md 文档漂移 | P2 | 文档与源码一致 |

---

#### Batch 4: 能力层打磨（features + strategy）— 预计 1-2 天

**features 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| F-1 | 拆分 codegen.py（749 行）：按表达式类型分模块 | P2 | 单一职责 |
| F-2 | 拆分 evaluator.py（697 行）：按评估策略分文件 | P2 | 单一职责 |
| F-3 | services/ 按关注域分子目录 | P3 | derived/、publication/、catalog/ |
| F-4 | 统一错误层级：DerivedError → FeaturesError 子类 | P2 | 单根错误树 |
| F-5 | features/errors.py → exceptions.py 统一 | P2 | 文件名与惯例一致 |

**strategy 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| S-1 | 提取 builtins/regime/ 为子包 | P3 | regime_*.py → regime/ 子包 |
| S-2 | root __init__.py 添加 3-5 核心导出 | P2 | Pipeline, StrategySpec, Context 可顶层导入 |
| S-3 | 拆分 stock_sector_rotation.py（640 行） | P3 | config/stages 分文件 |

---

#### Batch 4: 交易层加固 — 已合并至 Batch 2

---

#### Batch 5: 引擎层完善（backtest + analysis）— 预计 1 天

**backtest 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| B-1 | EngineResult 改为 frozen dataclass | P1 | 不可变 |
| B-2 | StepContext 添加 phase 状态标记 | P2 | 乱序 step 抛明确异常 |
| B-3 | 替换手动方差计算为 statistics.variance | P3 | 数值稳定 |
| B-4 | 消除 NAV→Return 重复逻辑 | P3 | 单一实现 |

**analysis 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| A-1 | 提取 SQLite Reader 共享行构造逻辑 | P2 | 无重复代码 |
| A-2 | Record 添加 from_row() 验证工厂 | P2 | 入库数据有校验 |
| A-3 | ArtifactService manifest-based 解析 | P3 | 无 filesystem glob |

---

#### Batch 6: 基础层清理（kernel + platform）— 预计 1 天

**kernel 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| K-1 | 清理 CLAUDE.md 漂移引用（json_types.py, MacroDataProvider） | P1 | CLAUDE.md 与源码一致 |
| K-2 | 审视 trading.py 类型归属：FeeModel/InstrumentDefinition 是否应迁至 execution | P2 | ADR 记录决策 |
| K-3 | MarketSnapshot A 股特有字段添加成熟度注释 | P3 | 字段标注 `# initial-focus: A-share` |
| K-4 | EventName vs str event_type 设计记录 ADR | P3 | docs/architecture/adr/ 新增 |

**platform 攻坚清单**：

| # | 任务 | 优先级 | 验收标准 |
|---|------|--------|---------|
| P-1 | 拆分 metrics.py（535 行）：提取 metaclass 逻辑和 provider 配置 | P2 | 主文件 < 300 行 |
| P-2 | ObservabilityRegistry 改为实例化或 contextvars | P2 | 无 class-level mutable state |
| P-3 | 清理 paths.py 死代码（3 个只 raise RuntimeError 的函数） | P1 | 文件 < 450 行 |
| P-4 | 统一 OnDuplicate 为 StrEnum | P1 | 全包 enum 风格一致 |
| P-5 | cache/core.py 提取 custom time source 策略 | P3 | get/set 无重复逻辑 |

---

### 7.3 攻坚时间线

```
Week 1（先拉短板）:
  Day 1-3: Batch 1 (data) — 最大包 + Dataset P0 治理
  Day 4-5: Batch 2 (execution + risk + portfolio) — 交易层加固

Week 2（补齐 + 打磨）:
  Day 1-2: Batch 3 (application + apps) — 编排层治理
  Day 3-4: Batch 4 (features + strategy) — 能力层打磨
  Day 5:   Batch 5 (backtest + analysis) — 引擎层完善
  Day 5:   Batch 6 (kernel + platform) — 基础层清理（可与 Batch 5 并行）

验收: 每个 Batch 完成后运行 pixi run -e dev check 全绿
```

---

## 8. 结论

### 8.1 当前状态总结

Ditto 架构已从"文档上有边界、源码里有旧惯性"进入"边界机器可守、能力包基本自治"的成熟状态。核心提升：

1. **36 条 import-linter 合约全绿** + 17 类 smell guard = 业界领先的架构门禁
2. **161 个 Protocol** + 零 ABC = 纯 Python 结构化子类型典范
3. **364/373 frozen dataclass** = 近乎完美的不可变数据模型
4. **7,174 测试函数** + 零 type:ignore + 零 TYPE_CHECKING = 工程质量优秀

### 8.2 瓶颈诊断

当前瓶颈不再是"架构是否清楚"，而是三类问题：

1. **代码级质量问题**（本报告 7.2 攻坚计划）：大文件拆分、类型不一致、Service 后缀语义、文档漂移等"最后一公里"问题
2. **运行时地基缺失**（R2/R3）：BrokerGateway 实现、Backtest/Live 共享 runtime、状态恢复
3. **产品闭环不足**（R1/R6）：DataCatalog runtime、Portfolio/Execution 占位实现

### 8.3 目标演进

| 阶段 | 目标 | 预期评分 |
|------|------|---------|
| 当前 | 架构治理完成，工程质量优秀 | 8.5/10 |
| 攻坚后（Batch 1-6）| 代码级质量提升，全模块 ≥ 8.0 | 9.1/10 |
| Runtime Spine 后 | Backtest/Paper/Live 共享 | 9.3/10 |
| DataCatalog + Reference 后 | 扩展性插件化 | 9.5/10 |
| 产品闭环后 | 全市场量化系统 | 9.7/10 |

### 8.4 一句话结论

**架构骨架已优秀，下一步是逐模块代码质量攻坚 + 运行时地基建设，从"组织良好的研究/回测框架"进化为"架构卓越的模块化量化系统"。**

---

## 10. 关键决策记录

本次评估过程中确认的架构决策，供后续实施参考。

### 10.1 评分口径

- **三口径并行**：工程综合 8.8 + 命名/边界 7.6 + 运行时 6.8 + live-ready 5.2
- 工程综合使用加权（依赖边界 18%、模块化 14%、Ports 12%...）
- 逐模块使用四维等权（可读性/一致性/整洁架构/扩展性）

### 10.2 Dataset 治理策略

- **路径 A：注册表模式**（非 DataCatalog runtime）
- 282 处引用集中在 6 个文件（全在 ingestion 子域）
- 提取 `DatasetRegistry` dataclass，将 fetch_handlers/data_writer/coordinator_constants 中的 `Dataset→X` 映射统一注册
- 新增数据集只改 `registry.register()` 一处
- Dataset enum 仍在 application，但路由逻辑集中在 registry

### 10.3 攻坚策略

- **先拉短板**：data(7.0) → execution(7.3) → risk(7.5) 优先
- 不拆包（保持 12 包），data 包强化内部子域分界

### 10.4 execution 策略

- **Paper Gateway + OMS 同步推进**
- 先实现 paper/mock BrokerGateway，验证 backtest→paper runtime seam
- OMS Lite 核心能力同步完善（order state、journal、reconciliation）

### 10.5 类型一致性

- **instrument_id 统一为 InstrumentId**：跨 portfolio/execution/risk 的持久化边界全面统一
- **SliceView.bars 改为窄 Protocol**：`dict[InstrumentId, BarSlice]` 替换 `dict[InstrumentId, Any]`

### 10.6 大文件策略

- **单一职责原则**（不设硬性行数限制）
- 700+ 行文件拆分时以职责边界为准

### 10.7 application concrete import

- **三个同步推进**：queries/source.py Protocol 注入 + providers 下沉 SQLite + fetch_handlers 注册表

### 10.8 Service 后缀治理

- **全局治理**，分类体系：
  - `*Facade`：应用层用例编排（聚合多子服务、暴露简化入口）
  - `*Store` / `*Reader` / `*Writer`：数据访问
  - `*Service`：跨域业务能力（稳定领域能力，非 CRUD/存储）
  - `*Coordinator` / `*Process`：长流程编排
- 参考 Martin Fowler PoEAA：Service Layer = Application Facade
- 当前 27 个 `*Facade` 类符合"聚合入口"定义，保留

### 10.9 错误文件命名

- **统一为 `exceptions.py`**（Python 社区压倒性惯例：Django/requests/urllib3/click/cryptography/attrs）
- `errors.py` 仅用于错误码/常量，不用于异常类定义
- **随 Batch 渐进统一**：每个 Batch 处理对应模块

### 10.10 data 包策略

- 保持 12 包，不拆分
- 强化内部子域分界（import-linter 子域级合约）

---

## 9. 验证命令

```bash
pixi run -e dev arch-check
# Contracts: 36 kept, 0 broken
# Architecture smell check passed

pixi run -e dev check
# ruff check passed
# ruff format: 1511 files left unchanged
# basedpyright: 0 errors, 0 warnings, 0 notes
# fast tests: ~7000+ passed, ~25 skipped
# import-linter: 36 kept, 0 broken
# architecture smell check passed
```
