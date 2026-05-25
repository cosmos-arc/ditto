# Ditto 架构攻坚最终计划

> 日期：2026-05-15
> 修订：2026-05-16
> 整合自：`docs/reviews/audit/2026-05-13-comprehensive-architecture-evaluation.md`、`docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md`、当前源码抽样复核
> 性质：面向后续实现的架构攻坚计划，不是单纯 review checklist
> 前置条件：B1-B9 整改已完成，Phase 1 Runtime Spine + Phase 2 OMS Lite 已落地

---

## 1. 当前判断

Ditto 现在不是“架构不清”的项目，而是一个已经具备强边界、强类型、强测试纪律的模块化量化平台雏形。下一阶段的关键不是继续证明 12 包结构正确，而是把三个短板补成长期可演进的能力：

1. **数据扩展路径**：`Dataset` enum 仍承担运行时目录职责；ingestion 的 fetch/write/instrument-support 路由散在多个 application 文件里。
2. **交易运行时闭环**：`BrokerGateway` 仍是 Protocol-only；`PaperSynchronizer.stream()` 未实现；execution reconciliation 仍是 summary dataclass。
3. **内部理解成本**：data/features/application 的大文件、Service/Store/Facade 命名语义、application concrete import、局部类型不一致，开始拉低可读性和变更安全。

总体方向应从“继续做架构洁癖”切换为：

> 以最小可运行闭环为牵引，沿真实扩展路径重构。命名、拆文件、异常文件名统一等工作只在能降低下一步风险时推进。

### 1.1 综合评分

| 口径 | 当前 | 目标 | 说明 |
|------|-----:|-----:|------|
| 工程综合质量 | **8.5/10** | 9.1 | 边界、测试、类型、不可变模型优秀 |
| 命名/边界/领域划分 | **7.6/10** | 8.8 | Protocol 归位有进展，Dataset 路由仍分散 |
| 模块化量化运行时就绪度 | **6.8/10** | 8.2 | Runtime Spine 起步，paper/live 仍未共享运行语义 |
| 全球全市场 live-ready | **5.2/10** | 7.2 | BrokerGateway、reconciliation、状态恢复仍不完整 |

### 1.2 逐模块评分

| 包 | 综合 | 可读性 | 一致性 | 整洁架构 | 扩展性 | 主要短板 |
|---|:----:|:------:|:------:|:-------:|:------:|---|
| kernel | **8.6** | 9 | 9 | 9 | 8 | `trading.py` 未来膨胀、EventName 语义 |
| platform | **7.7** | 8 | 7 | 8 | 8 | observability/config 复杂度、ABC/Protocol 策略 |
| data | **7.0** | 7 | 7 | 7 | 7 | Dataset 扩展路径、服务命名、大文件 |
| features | **8.5** | 9 | 9 | 8 | 9 | codegen/evaluator 大文件、错误根分裂 |
| strategy | **8.6** | 9 | 9 | 9 | 8 | regime/template 组织可继续收敛 |
| portfolio | **7.7** | 8 | 7 | 8 | 8 | market_value 语义、InstrumentId 类型一致性 |
| risk | **7.4** | 8 | 7 | 8 | 7 | `SliceView.bars` 过宽、RiskGate 未成形 |
| execution | **7.2** | 8 | 7 | 7 | 7 | gateway/reconciliation/paper 闭环不足 |
| backtest | **8.8** | 9 | 9 | 9 | 9 | EngineResult 可变、phase guard |
| analysis | **7.8** | 9 | 9 | 8 | 7 | 研究 artifact/index 能力偏薄 |
| application | **7.7** | 8 | 9 | 7 | 8 | concrete import、第二 composition root 倾向 |
| apps | **8.2** | 8 | 9 | 9 | 8 | registry/startup 可继续拆清 |

### 1.3 源码快照

| 指标 | 值 |
|------|-----:|
| 生产源码文件 | 897 |
| 生产源码行数 | 103,425 |
| 测试文件 | 686 |
| 测试函数 | 7,174 |
| Protocol class definitions | 121 |
| ABC class definitions | 2（`NotificationSender`, `ConfigInitProvider`） |
| frozen dataclass | 364（/373 total） |
| `type: ignore` | 0 |
| `TYPE_CHECKING` | 0 |
| pandas import | 0 |
| import-linter 合约 | 36 kept, 0 broken |
| `@traced` | 195 处 |
| `noqa` | 70 |
| Dataset lines in application | 263 行 / 16 文件 |

---

## 2. 业界对标结论

本计划采用“借鉴原则，不照搬形态”的方式对标。Ditto 是 Python 3.13 + Polars + 12 包模块化单体，不应把外部平台的全部目录结构搬进来。

| 参考 | 业界实践 | 对 Ditto 的结论 |
|------|----------|----------------|
| Cockburn Ports & Adapters | 应用内核通过 ports 与外部设备/数据库隔离，可用 mock adapter 独立测试 | `BrokerGateway`、数据源、存储应是 adapter-facing；application 用例不应直接知道具体 Tushare/SQLite 实现 |
| Fowler Service Layer | Service Layer 定义 application boundary 并协调一次操作响应 | `application.processes/commands/queries` 才是用例服务层；data 内部 `*Service` 不应冒充 application service |
| Fowler Repository/Gateway/Registry | Repository 隔离持久化集合访问；Gateway 封装外部资源；Registry 可集中查找公共对象 | `*Store` 适合 Reader/Writer 组合；`BrokerGateway` 适合券商 adapter；`IngestionDatasetRegistry` 适合集中 ingestion 路由，但不能变成全局 service locator |
| Microsoft DDD 分层 | application layer 保持薄，只协调任务，不持有业务规则；repository interface 应避免让应用依赖基础设施实现 | `application` 可以编排 data/features/execution，但不应装配 SQLite reader/source adapter 细节；这些应下沉到 `apps.registry` 或能力包 DI |
| LEAN / QuantConnect | backtest/live 尽量保持一致，数据 provider 和 brokerage 是可替换配置 | Ditto 应优先做 paper runtime parity，而不是只扩回测能力 |
| NautilusTrader | common core 被 backtest/sandbox/live 共享，策略可无代码变化迁移；live reconciliation 是独立关注点 | Ditto 应把 execution/risk/portfolio 的运行语义抽成可共享 spine；reconciliation 不应只是报表 DTO |
| OpenBB | provider/extension 可安装、可发现、可覆盖；provider 可以独立执行 | DatasetRegistry 是正确方向，但短期应先服务 ingestion 用例；中期再演进 `data.catalog` runtime |
| vn.py / VeighNa | gateway + event engine + OMS cache 形成交易端产品闭环 | Ditto 的 gateway conformance、event journal、account/order/fill 同步比新增研究功能更紧迫 |
| FinRL-X | weight-centric pipeline 强调 strategy/backtest/broker execution deployment consistency | 保持 `strategy -> TargetPortfolio/Signal` 的 weight-centric 方向，AI/RL 未来作为 strategy/allocator plugin，不侵入 execution |

**关键校准**：

- `DataCatalog runtime` 是中期目标，不是当前 Batch 1 的第一刀。第一刀应是 `application.processes.ingestion` 内的 `IngestionDatasetRegistry`。
- `Facade` 不是越多越优雅。只有跨多个内部组件、能显著稳定上层 API 的入口才建 Facade；纯 1-line pass-through 应避免。
- `PaperBrokerGateway` 属于 execution adapter-facing 实现；`PaperTradingRuntime/PaperSynchronizer` 属于 application/runtime use-case 编排；不要把 runtime loop 塞进 gateway。

---

## 3. 架构决策

### 3.1 攻坚优先级

优先级不是按“分数最低”机械排序，而是按“是否解锁真实扩展路径”排序：

1. **Dataset ingestion 路由收敛**：这是新增数据集、多 provider、多质量 profile 的前置。
2. **Paper trading 最小闭环**：这是 backtest/paper/live parity 的前置。
3. **Application composition boundary**：这是 ports/adapters 能否长期成立的前置。
4. **类型一致性和拆文件**：只在触达路径上推进，防止重构变成命名搬家。

### 3.2 Dataset 治理

采用两阶段路线：

**阶段 1：`IngestionDatasetRegistry`（当前计划）**

- 位置：`ditto_application.processes.ingestion.dataset_registry`。
- 职责：声明 dataset 的 ingestion-time metadata：daily fetch、instrument fetch、write route、instrument support、date schedule、quality profile key。
- 目标：替换 `fetch_handlers.py`、`data_writer.py`、`coordinator_constants.py` 中重复的 `Dataset -> X` 映射。
- 约束：registry 不依赖具体 Tushare/FRED 类，只依赖现有 `SourceFetchers` 和窄 fetcher Protocol。

**阶段 2：`data.catalog` runtime（后续）**

- 位置：`ditto_data.catalog`。
- 职责：纯数据目录 metadata：dataset id、schema、asset class、partition/date semantics、lineage、maturity。
- 禁止：不能依赖 application ingestion、fetcher、writer、quality engine 实现。

`Dataset` enum 暂保留为稳定 ID，但逐步去掉运行时行为。`asset_class`、`date_schedule`、`supports_instrument_ingestion()` 迁移方向是 registry/catalog metadata，而不是继续堆 enum property。

### 3.3 Data 内部命名

命名治理采用“职责证明优先”，不是全局强制 Facade 化。

| 名称 | 使用条件 | 禁止 |
|------|----------|------|
| `*Store` | Reader/Writer 组合、集合式数据访问、零业务编排 | 混入校验、富化、跨表工作流 |
| `*Service` | 有非平凡业务/应用内编排：验证、富化、并发、跨组件协调 | 只有 1-line pass-through |
| `*Facade` 或领域名词入口 | 聚合多个内部组件，并给上层稳定、粗粒度 API | 为了隐藏 `Service` 后缀创建空转代理 |
| `*Coordinator` / `*Process` | 长流程、跨步骤 orchestration | 持有底层持久化细节 |
| `*Gateway` | 外部系统 adapter boundary | 承担 use-case runtime loop |
| `*Registry` | 集中声明静态/半静态路由或元数据 | 变成到处可取对象的 service locator |

因此，原计划中的“Market/Capital/Fundamental/Macro/Metadata/Ingestion 全部变领域名词 Facade”需要收敛：

- `MetadataService` 可保留为 Facade 候选，因为它确实聚合 calendar/instrument/universe。
- `MarketService` 与 `MarketWriteService` 可先保留，除非上层调用已经因读写双入口显著复杂。
- `CapitalService`、`FundamentalService` 若只是 Reader/Writer 组合，优先改 `CapitalStore`、`FundamentalStore`。
- ingestion runtime stores 优先改名为 `IngestionCursorStore`、`IngestionLogStore`、`FreezeStore`、`QualityRecordStore`。
- `SourceService` 若职责是数据源查找/访问，优先改 `SourceGateway` 或 `SourceAccessor`；若承担 provider registry，则命名为 `SourceRegistry`。

### 3.4 Application concrete import

`application` 可以依赖能力包的公开服务、Protocol 和 use-case DTO，但应避免直接装配物理实现。目标不是让 `application` 零 concrete import，而是防止它成为第二个 composition root。

需要迁出的典型对象：

- `SQLiteClient`
- `ditto_data.storage.*` Reader/Writer
- 具体 source adapter：`TushareSource`、`FredSource`、`TdxSource`
- feature runtime store concrete reader/writer

允许保留的对象：

- capability package 的应用级服务或公开 facade
- command/query/process 自身的 use-case 类型
- 已经由 capability package 定义的窄 Protocol

迁移落点优先级：

1. `apps.registry.*`：部署时具体实现和 DI 装配。
2. capability package `di/`：能力包内部具体存储装配。
3. application 本地 Protocol：当 use case 只需要很窄的行为，且消费者拥有 port。

### 3.5 Paper runtime

拆成三层，避免 gateway 和 runtime loop 混在一起：

| 层 | 位置 | 职责 |
|----|------|------|
| `PaperBrokerGateway` | `ditto_execution.broker.gateways.paper` | 实现 `BrokerGateway`：connect/get_account/submit/cancel/query_fills；使用 OMS/order book/fill store/account view |
| `ExecutionReconciler` | `ditto_execution.reconciliation` | 对比 expected orders/fills 与 broker actual state，输出 typed diff/report |
| `PaperTradingRuntime` / `PaperSynchronizer` | `ditto_application.runtime` 或 `processes.execution` | 串起 signal -> plan -> risk -> order -> gateway -> fill -> account view |

`PaperSynchronizer.stream()` 的最小版本可以只是按显式 clock/time-slice 产生 deterministic slices；它不应直接知道券商适配细节。

### 3.6 类型一致性

- 跨核心包的 `instrument_id` 统一使用 `InstrumentId`。
- storage/SQLite/外部 API 边界可以转换为 `int`/`str`，但转换必须集中在 adapter/mapper。
- `risk.post_trade.SliceView.bars` 必须从 `Any` 改为窄 `BarSlice` Protocol。
- backtest/report 对外结构若被 portfolio/application 消费，应通过 Protocol 或 read model 解耦。

### 3.7 低 ROI 清理降级

以下工作不作为架构攻坚主线，只随触达治理：

- `errors.py` / `exceptions.py` 全库统一。
- root `__init__.py` 增减导出。
- 仅为降行数拆文件。
- 仅为名字好看创建 Facade。
- ABC 全部转 Protocol。两个 ABC 可先写 ADR 决定策略。

---

## 4. 统一 Review 检查清单

每个 Batch 必须回答这些问题：

| 维度 | 检查项 |
|------|--------|
| 边界 | 是否新增违反 `.importlinter` 的具体依赖？是否把 composition root 逻辑放进 application？ |
| 抽象 | Protocol 是否由消费者拥有？是否足够窄？是否只是为了测试而过度抽象？ |
| 数据 | Dataset 行为是否从 enum 迁出？registry 是否避免依赖具体 source/storage？ |
| Runtime | backtest/paper/live 语义是否更一致？gateway 是否只做 adapter-facing 工作？ |
| 类型 | 是否引入 `Any`、`type: ignore`、`TYPE_CHECKING`？跨包 id 是否为 `InstrumentId`？ |
| 命名 | Store/Service/Facade/Gateway/Registry 是否有职责证明？ |
| 错误 | 业务返回值、异常、reconciliation diff 是否语义分离？ |
| 测试 | 是否有 RED/GREEN 证据？是否覆盖错误路径、partial fill、cancel、unsupported dataset？ |
| 文档 | CLAUDE.md/ADR 是否随架构变化更新？是否记录暂不做的选择？ |

**禁止项**：

- 禁止把 `IngestionDatasetRegistry` 下沉到 `data` 后再让它依赖 application fetcher/writer。
- 禁止让 `PaperBrokerGateway` 驱动完整 trading runtime loop。
- 禁止创建只有 pass-through 的领域名词 Facade。
- 禁止用 `TYPE_CHECKING` 解决拆分后的循环依赖。
- 禁止为了异常文件名统一做大规模 import churn。

---

## 5. 攻坚计划

### 总体策略

- Week 1 只打两条关键路径：Dataset ingestion 扩展路径 + Paper 最小交易闭环。
- 每个 Batch 独立可验证，完成后 `pixi run -e dev check` 全绿。
- 大文件拆分只跟随当前改动路径，不做无业务收益的机械拆分。
- 每个 Batch 必须能用一条“新增能力”描述，而不是只描述“改了多少名字”。

---

### Batch 1: Ingestion Dataset Registry + Data 命名收敛 — 3-4 天

**目标**：新增数据集的 ingestion 路由从多点修改变成单点声明，同时修正 data 内部 Store/Service 命名中最误导的部分。

#### Batch 1A: `IngestionDatasetRegistry`（P0）

| # | 任务 | 验收标准 |
|---|------|----------|
| D1A-1 | 新增 `DatasetRegistration`、`IngestionDatasetRegistry`、`WriteKind`、daily/instrument fetch context | registry 可注册、覆盖、查询 dataset；unsupported dataset 报清晰异常 |
| D1A-2 | 用 registry 替换 `fetch_handlers.py` daily/instrument 映射 | daily 和 instrument fetch 的现有测试通过；新增 mock dataset 只改 registry |
| D1A-3 | 用 registry 替换 `coordinator_constants.SUPPORTED_INSTRUMENT_DATASETS` | instrument support 来源唯一 |
| D1A-4 | 用 registry 驱动 `IngestionDataWriter` 写入分派 | write route 来源唯一；fundamental/capital/market/metadata/macro 路由覆盖完整 |
| D1A-5 | 把 `Dataset.date_schedule` 使用点改为 registry metadata | `ingest_range()` 不再依赖 enum behavior |

#### Batch 1B: Data Store/Service 命名（P1）

只改职责明显不匹配的类，避免一次性全局 Facade 化。

| # | 任务 | 验收标准 |
|---|------|----------|
| D1B-1 | `CapitalService` -> `CapitalStore`（若确认为纯 Reader/Writer 组合） | 无业务逻辑类不再叫 Service；引用更新 |
| D1B-2 | `FundamentalService` -> `FundamentalStore`（若确认为纯 Reader/Writer 组合） | 引用更新；测试覆盖查询/写入 |
| D1B-3 | ingestion runtime services 改 Store：Cursor/Log/Freeze/QualityRecord | 命名表达持久化状态集合 |
| D1B-4 | `SourceService` 职责复核后命名为 `SourceAccessor` / `SourceRegistry` 二选一 | 名称与职责一致，避免“Service”泛化 |
| D1B-5 | 保留 `MarketService`、`MarketWriteService`、`MacroService`、`MetadataService`，除非拆分证据充分 | 不制造空转 Facade |

#### Batch 1C: 触达式拆分（P1/P2）

| # | 任务 | 验收标准 | 状态 |
|---|------|----------|------|
| D1C-1 | 拆分 `data/services/metadata/instrument.py` 中被当前改动触达的查询/写入/校验块 | 单一职责；行为等价测试 | ⏭️ 跳过：未被 Batch 1A/1B 触及 |
| D1C-2 | 拆分 `data/storage/base/sqlite_store.py` 的 DDL/helper，仅当 registry/store rename 触达 | helper 有独立单元测试 | ⏭️ 跳过：未被 Batch 1A/1B 触及 |
| D1C-3 | 拆分 `instrument_reader.py` 查询构造和 row mapping，仅当类型迁移触达 | mapper 可单测 | ⏭️ 跳过：未被 Batch 1A/1B 触及 |
| D1C-4 | 清理空壳 `providers/` 或把残留状态写入 CLAUDE.md | 无误导性空 namespace | ✅ 完成 |
| D1C-5 | 更新 `packages/data/CLAUDE.md` 和 architecture standards | 文档与新命名一致 | ✅ 完成 |

**完成标准**：

- `pixi run -e dev check` 全绿。
- 新增一个 mock dataset 的 fetch/write/instrument-support 测试只需要改 registry。
- `Dataset` enum 不再是 ingestion runtime 行为唯一来源。
- 没有新增跨包 re-export、`TYPE_CHECKING`、`Any`。

---

### Batch 2: Paper Trading Runtime + Execution/Risk/Portfolio 类型闭环 — ✅ 已完成（2026-05-17）

**目标**：形成最小 paper 交易闭环，并把交易端最关键的类型和状态恢复缺口补上。

#### Batch 2A: `PaperBrokerGateway`（P0）— ✅ 完成

| # | 任务 | 验收标准 | 状态 |
|---|------|----------|------|
| E2A-1 | 实现 `ditto_execution.broker.gateways.paper.PaperBrokerGateway` | 满足 `BrokerGateway` Protocol | ✅ |
| E2A-2 | `submit_order()` 写入 order book/journal 并返回 `OrderTicket` | order event 注入模式与 submit/cancel/update 一致 | ✅ |
| E2A-3 | `cancel_order()` 覆盖 open/partial/nonexistent 状态 | cancellation 测试覆盖 | ✅ |
| E2A-4 | `query_fills()` 返回 gateway-reported fills | partial fill、full fill、no fill 均有测试 | ✅ |
| E2A-5 | broker adapter conformance tests | 后续 QMT/XTP/IBKR adapter 可复用同一套行为测试 | ✅ |

#### Batch 2B: Reconciliation（P0）— ✅ 完成

| # | 任务 | 验收标准 | 状态 |
|---|------|----------|------|
| E2B-1 | `ReconciliationReport` 从 summary DTO 扩展为 typed report + diff entries | expected/actual/unmatched/mismatched 可表达 | ✅ |
| E2B-2 | 新增 `ExecutionReconciler` | 可对比 expected orders/fills 与 broker actual fills | ✅ |
| E2B-3 | 定义 mismatch 类型：missing fill、extra fill、qty mismatch、price mismatch、status mismatch | 每类至少一个单测 | ✅ |
| E2B-4 | 记录 recovery policy 为后续 ADR，不在本 Batch 自动修复状态 | 避免过早写 repair flow | ✅ |

#### Batch 2C: Paper runtime 最小流（P0/P1）— ✅ 完成

| # | 任务 | 验收标准 | 状态 |
|---|------|----------|------|
| E2C-1 | 实现 `PaperSynchronizer.stream()` 的 deterministic time-slice 最小版本 | 不再 `NotImplementedError`；可由测试 clock 驱动 | ✅ |
| E2C-2 | 新增 `PaperTradingRuntime`，串起 order -> gateway -> fill -> account view | 一个 smoke test 覆盖完整路径 | ✅ |
| E2C-3 | 明确 runtime 只编排，不实现 gateway 细节 | import 方向符合 application -> execution | ✅ |
| E2C-4 | 加入 account view 快照断言 | fill 后 cash/position/exposure 更新正确 | ✅ |

#### Batch 2D: Risk/Portfolio 类型修正（P1）— ✅ 完成

| # | 任务 | 验收标准 | 状态 |
|---|------|----------|------|
| R2D-1 | `SliceView.bars` 改为 `Mapping[InstrumentId, BarSlice]` | 无 `Any`；risk 仍不依赖 backtest | ✅ |
| R2D-2 | 设计最小 `RiskGate` Protocol：pre-submit、pre-cancel、post-fill、daily-scan | 先定义 port 和 ADR | ✅ |
| PF2D-1 | 修正 sell path `market_value` 语义 | 使用 fill price 语义 | ✅ |
| PF2D-2 | `Account` 去掉误导性 `@dataclass` | 装饰器与实现一致 | ✅ |
| PF2D-3 | holdings/positions snapshot 的 `instrument_id` 统一为 `InstrumentId` | 类型安全 | ✅ |

**完成标准验证**：

- ✅ `pixi run -e dev check` 全绿（6631 passed, 36/36 contracts, 0 type errors）。
- ✅ 策略目标组合能跑通 order -> paper fill -> account view。
- ✅ cancellation、reconciliation mismatch 有测试（16 reconciliation + 20 gateway tests）。
- ✅ `execution` 不依赖 `risk`；`risk` 不依赖 `execution`；`backtest` 不导入真实 broker gateway。

---

### Batch 3: Application Composition Boundary — ✅ 已完成（2026-05-18）

**目标**：application 保持用例编排层，不再承担具体基础设施装配。

| # | 任务 | 优先级 | 验收标准 | 状态 |
|---|------|:------:|----------|------|
| AP-1 | `queries/source.py` 定义 `SourceDataPort` Protocol，移除 `TushareSource | FredSource` 暴露 | route-visible source data 通过 Protocol 获取 | ✅ |
| AP-2 | `providers_command.py` 中 `TdxSource`、`InstrumentReader`、`ComparisonWriter` 改用 Protocol 类型 | command provider 不直接装配 storage/source concrete | ✅ |
| AP-3 | `providers_process.py` 中 `SQLiteClient` 改用 `SQLiteCompileCacheBackend` Protocol | application process provider 不成为 infra composition root | ✅ |
| AP-4 | DatasetRegistry 与 Batch 1 集成验证 | 无重复 Dataset 映射 | ✅ |
| AP-5 | `data_writer.py`、`backtest_process.py` 拆分评估 | 当前改动未触达，跳过 | ⏭️ |
| APP-1 | `apps/registry/init_providers.py` 迁到 `registry/infra/` | apps registry 结构更清楚 | ✅ |

**完成标准验证**：

- ✅ application 零 concrete storage/source/SQLiteClient import（6 个全部消除）
- ✅ 新增 import-linter 合约 `application-no-concrete-infra`（37 kept, 0 broken）
- ✅ `ProtocolAdapterProvider` 在 `apps/registry/infra/` 桥接 concrete → Protocol
- ✅ `pixi run -e dev check` 全绿（6629 passed, 37/37 contracts, 0 type errors）

---

### Batch 4: Features + Strategy 触达式可读性打磨 — ✅ 已完成（2026-05-18）

**目标**：降低最热路径文件理解成本，统一错误语义。

| # | 任务 | 优先级 | 验收标准 | 状态 |
|---|------|:------:|----------|------|
| F-1 | 拆分 `features/expression/codegen.py`：visitor + polars expr builders | 行为等价；compiler tests 全绿 | ✅ |
| F-2 | 拆分 `features/evaluation/evaluator.py`：orchestrator + helpers | evaluation tests 全绿 | ✅ |
| F-3 | `DerivedError` 改为 `FeaturesError` 子类 | 单根错误树；兼容捕获测试 | ✅ |
| F-4 | `services/` 按 derived/publication 重新组织 | 降级：barrel `__init__.py` 已提供清晰 API，ROI 不足 | ⏭️ |
| S-1 | strategy regime 子包化（`alpha/builtins/regime/`） | 不破坏 strategy 零依赖上游能力包 | ✅ |

**完成标准验证**：

- ✅ `pixi run -e dev check` 全绿（6630 passed, 0 failed, 0 type errors, arch check passed）
- ✅ `codegen.py`（750行）拆为 `codegen/__init__.py` + `_visitor.py`（230行）+ `_builders.py`（480行）
- ✅ `evaluator.py`（697行）拆为 `evaluator/__init__.py` + `_orchestrator.py` + `_helpers.py`
- ✅ `DerivedError` → `FeaturesError` 子类，单根错误树建立
- ✅ regime 核心文件移入 `builtins/regime/` 子包，外部导入路径不变
- ✅ 无新增 `TYPE_CHECKING`、`Any`、跨包 re-export

---

### Batch 5: Backtest + Analysis 可复现性 — ✅ 已完成（2026-05-18）

| # | 任务 | 优先级 | 验收标准 | 状态 |
|---|------|:------:|----------|------|
| B-1 | `EngineResult` 改 frozen dataclass，运行中状态另建 builder | 不可变结果；回测测试全绿 | ✅ |
| B-2 | `StepContext` 添加 required getter 或 phase guard | 乱序 step 抛明确异常 | ✅ |
| B-3 | 消除 NAV -> Return 重复逻辑 | 单一实现 | ✅ |
| A-1 | analysis SQLite Reader 提取共享 row factory | 无重复行构造 | ✅ |
| A-2 | Record 添加 `from_row()` 验证工厂 | 入库数据有校验 | ✅ |
| A-3 | ArtifactService manifest/index 驱动作为后续设计（ADR） | 不把 research artifact 过早产品化 | ✅ |

**完成标准验证**：

- ✅ `pixi run -e dev check` 全绿（lint + fmt + type + test --fast + arch-check）
- ✅ `EngineResult` frozen，orders/fills 为 tuple，新增 `EngineResultBuilder` 可变累积器
- ✅ `StepContext` 新增 `require_slice/account_view/execution_plan/target_portfolio()` 类型安全 getter
- ✅ 提取 `safe_ratio()`、`total_return()` 共享辅助函数，消除 9 处重复 NAV/Return 计算
- ✅ 4 种 Record 类型新增 `from_row()` 验证工厂，reader 6 个方法重构为单行调用
- ✅ ADR `docs/architecture/adr-research-artifact-manifest.md` 记录 manifest/index 演进策略
- ✅ 37/37 import-linter 合约保持，无新增 `TYPE_CHECKING`、`Any`、跨包 re-export

---

### Batch 6: Kernel + Platform 基础层清理 — ✅ 已完成（2026-05-18）

| # | 任务 | 优先级 | 验收标准 | 状态 |
|---|------|:------:|----------|------|
| K-1 | 清理 kernel CLAUDE.md 漂移引用 | 文档与源码一致 | ✅ |
| K-2 | 为 `trading.py` 类型归属做 ADR | 记录哪些共享交易语言可留 kernel | ✅ |
| K-3 | `MarketSnapshot` A 股字段标注 initial-focus maturity | 全球市场扩展风险显式化 | ✅ |
| K-4 | `EventName` vs `DomainEvent.event_type: str` 写 ADR | 类型安全决策可追溯 | ✅ |
| P-1 | 拆分 `platform/foundation/observability/metrics.py` registry/definition/provider binding | 主路径复杂度下降 | ✅ |
| P-2 | `ObservabilityRegistry` 改实例化或 contextvars | 无 class-level mutable runtime state | ✅ |
| P-3 | 清理 `paths.py` 死代码 | 文件收缩，行为不变 | ✅ |
| P-4 | `OnDuplicate` 改 `StrEnum` | enum 风格一致 | ✅ |
| P-5 | `ConfigInitProvider` / `NotificationSender` 写 ADR 或转 Protocol | ABC/Protocol 策略统一 | ✅ |

**完成标准验证**：

- ✅ `pixi run -e dev check` 全绿（6702 passed, 37/37 contracts, 0 type errors）
- ✅ kernel CLAUDE.md 与源码完全一致（修复 7 处漂移引用）
- ✅ 2 个 ADR 文档记录 trading.py 归属和 EventName 决策
- ✅ MarketSnapshot 标注 A-share initial-focus maturity
- ✅ metrics.py（534行）拆为 metrics/ 包（_types.py + _registry.py + _binding.py）
- ✅ ObservabilityRegistry 从 class-level state 改为模块级单例实例
- ✅ 项目零 ABC（ConfigInitProvider + NotificationSender → Protocol）
- ✅ OnDuplicate 改 StrEnum，enum 风格统一
- ✅ paths.py 删除 34 行死代码
- ✅ 无新增 `TYPE_CHECKING`、`Any`、跨包 re-export

**降级项**：全库 `errors -> exceptions` 不在本批强制。

---

## 6. 时间线

```text
Week 1:
  Day 1-2: Batch 1A - IngestionDatasetRegistry
  Day 3-4: Batch 1B/1C - Data 命名与触达式拆分
  Day 5:   Batch 2A - PaperBrokerGateway + conformance tests

Week 2:
  Day 1:   Batch 2B - ExecutionReconciler
  Day 2:   Batch 2C/2D - Paper runtime + Risk/Portfolio 类型闭环
  Day 3:   Batch 3 - Application composition boundary
  Day 4:   Batch 4 - Features/Strategy 热点打磨
  Day 5:   Batch 5/6 - Backtest/Analysis + Kernel/Platform，可并行拆分
```

若 Batch 2 发现 OMS/event journal 状态模型不足，应暂停后续打磨类任务，先补 ADR 和最小状态恢复设计。

---

## 7. 预期收益

| 阶段 | 工程架构 | 运行时 | 可读性 | 扩展性 |
|------|:-------:|:-----:|:-----:|:-----:|
| 当前 | 8.5 | 6.8 | 8.0 | 7.8 |
| Batch 1 后 | 8.7 | 6.9 | 8.2 | 8.3 |
| Batch 2 后 | 8.8 | 7.6 | 8.3 | 8.4 |
| Batch 3 后 | 8.9 | 7.7 | 8.4 | 8.6 |
| Batch 4-6 后 | **9.1** | **8.0** | **8.8** | **8.8** |

评分提升不是核心目标。真正的收益是：

- 新增 dataset/provider 不再穿透多处映射。
- paper trading 有可运行 adapter/runtime/reconciliation 骨架。
- application 不再继续吸收具体基础设施装配。
- Store/Service/Facade 命名开始有可执行判定标准。
- 后续真实 QMT/XTP/IBKR gateway 有 conformance test 基线。

---

## 8. 验证命令

每个代码 Batch 完成后必须运行：

```bash
pixi run -e dev check
```

应包含：

```text
ruff check passed
ruff format passed
basedpyright: 0 errors
fast tests passed
import-linter: 36 kept, 0 broken
architecture smell check passed
```

文档/架构类改动至少运行：

```bash
pixi run -e dev arch-check
```

Batch 1 额外建议：

```bash
pixi run -e dev test packages/application/tests -k "ingestion or dataset_registry"
```

Batch 2 额外建议：

```bash
pixi run -e dev test packages/execution/tests packages/portfolio/tests packages/risk/tests -k "paper or broker or reconcile or fill or account"
```

---

## 9. 风险与约束

1. **不改 12 包结构**：所有攻坚在现有包内完成。
2. **不引入新依赖**：除已有 pyproject/pixi 配置中的库外不新增。
3. **不放松 import-linter**：36 条现有合约不变，可新增 smell 合约。
4. **不做空转 Facade**：Facade 必须降低上层认知成本或稳定 API。
5. **不把 registry 当 service locator**：registry 只声明 dataset route metadata。
6. **不提前做真实 live gateway**：先 paper/mock gateway + conformance，真实券商后续接。
7. **不为命名统一牺牲变更安全**：异常文件名、barrel 导出、行数拆分只随触达治理。
8. **不绕过 TDD**：P0/P1 任务必须先有失败测试或 characterization test。

---

## 10. 来源与依据

| 来源 | 用途 |
|------|------|
| `docs/reviews/audit/2026-05-13-comprehensive-architecture-evaluation.md` | 逐模块深度审计、指标基线、源码热点 |
| `docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md` | 事实校正、runtime 闭环、Dataset 路由、业界对标 |
| `docs/architecture/boundaries-and-abstraction-standards.md` | Ditto 内部分层、命名、抽象层级规范 |
| `docs/architecture/adr-runtime-spine.md` | runtime spine 既有决策 |
| `docs/superpowers/plans/2026-05-14-dataset-registry-ingestion.md` | DatasetRegistry 已有实现计划，Batch 1A 应与其对齐 |
| Alistair Cockburn, Hexagonal Architecture | Ports & Adapters、mock adapter、inside/outside boundary |
| Martin Fowler PoEAA Catalog | Service Layer、Repository、Gateway、Registry 命名语义 |
| Microsoft DDD Microservices Guide | application layer 薄编排、domain/infrastructure 分离 |
| NautilusTrader docs | common core、backtest/sandbox/live 共享语义、execution reconciliation |
| QuantConnect LEAN docs | backtest/live consistency、brokerage/data provider 配置 |
| OpenBB docs | provider extension、coverage registry、provider 独立安装/发现 |
| vn.py / VeighNa docs | gateway、event engine、OMS state cache 的交易产品闭环 |
