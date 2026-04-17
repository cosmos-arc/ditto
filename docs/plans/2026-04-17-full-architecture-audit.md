# Ditto 全维度架构审计计划

> **日期**：2026-04-17
> **范围**：全部 7 个包，自底向上 6 Phase
> **目标**：目标架构蓝图 + 每模块审计报告 + P0-P3 发现清单 + 逐模块修复计划

---

## 1. Context

经过深入的架构重构和功能补全（v1 sprint），项目已有 7 个包、1,276 文件、248K 行代码。用户对各模块的职责清晰度、命名一致性、架构合规性、与业界最佳实践的差距仍不确定。本审计旨在系统性地识别所有架构/编码问题。

---

## 2. 对标基准

### 2.1 对标平台全景

#### Tier 1：生产级量化交易引擎（架构深度对标）

| 平台 | 核心架构模式 | 关键设计 | Ditto 可借鉴 |
|------|-------------|---------|-------------|
| **QuantConnect LEAN** | 5 层 Framework（Universe→Alpha→Portfolio→Risk→Execution），C# + Python wrapper | Dependency Inversion（上层定义接口、下层实现），Config-Driven Pipeline | 5 层 Pipeline 解耦思路已借鉴（Ditto 8 Stage 更细粒度） |
| **NautilusTrader** | Hexagonal + DDD，Rust 核心引擎 + Python 控制面 | 单线程内核 + MessageBus pub/sub，严格 backtest-live parity，Component FSM 生命周期 | DDD 值对象建模（Price/Quantity/Money），Port/Adapter 模式，FSM 生命周期 |
| **Microsoft Qlib** | Config-Driven Pipeline Engine（CDPE），线性管线 | 表达式引擎（AST 解析 + LRU 缓存 + 2 级磁盘缓存），DataHandler pipeline | 表达式缓存策略，Processor chain 模式，DataHandlerLP 训练/推理分离 |

#### Tier 2：数据/因子平台（数据架构对标）

| 平台 | 核心架构模式 | 关键设计 | Ditto 可借鉴 |
|------|-------------|---------|-------------|
| **OpenBB** | Microkernel + Plugin（6 类扩展），Poetry entry points | TET 管线（Transform-Extract-Transform），Metamodel 标准化（同一接口多 provider），ProviderInterface Singleton | 数据源标准化接口，Provider 可插拔替换 |
| **Databento** | Thin Client + Binary Protocol，零计算客户端 | DBN 二进制编码（零拷贝），统一 live/historical schema，PIT Symbology 内置 | 统一数据模型（batch/stream 同 schema），零拷贝反序列化 |

#### Tier 3：因子研究 / AI 增强平台（功能对标）

| 平台 | 核心架构模式 | 关键设计 | Ditto 可借鉴 |
|------|-------------|---------|-------------|
| **Zipline (Quantopian)** | Pipeline DAG（Factor/Filter/Classifier 三原语），计算图优化 | DataPortal 统一门面，Bundle 数据包，向量化执行 | Pipeline DAG 依赖分析，Dataset 抽象 |
| **PandaAI-Tech (panda_factor)** | 双层架构（factor 研究 + workflow 执行），微服务 | 表达式 DSL 因子定义，`@work_node` 插件系统，Pydantic I/O 验证 | 因子 DSL 对比（Ditto 编译器 vs 运行时解析），插件节点模式 |
| **daily_stock_analysis** | 单体 Pipeline + LLM 增强，GitHub Actions 零成本部署 | 多源适配器 + 优先级 fallback，LiteLLM 多 provider，fail-open 降级 | 数据源 fallback 链设计，LLM 集成模式 |
| **QSTrader** | 事件驱动 + 模块化，Alpha→Portfolio→OrderSizer→Broker | 调度与再平衡分离，Alpha Model 接口（forecast weights） | 简洁的 pipeline 链路参考 |
| **TradeAgent** | 单体批处理 + LLM Sentiment | Claude 3.5 Sonnet 新闻情绪分析，Alpaca 适配器 | LLM 情绪分析集成参考（非架构参考） |

#### Tier 4：架构方法论对标

| 方法论 | 核心原则 | Ditto 适用点 |
|--------|---------|-------------|
| **Clean Architecture** | 依赖永远指向内层，Domain 零外部依赖 | Kernel/Engine 的纯粹性验证 |
| **Hexagonal (Ports & Adapters)** | Domain 定义 Port，Infra 实现 Adapter | Data sources 适配器模式，DataProvider Protocol |
| **DDD** | Aggregate Root / Value Object / Domain Event / Domain Service | Engine 领域建模审查 |
| **CQRS (Cosmic Python)** | Command 走 Domain Model，Query 走直接 DTO | App 层 CQRS 四象限审查 |

### 2.2 业界对标综合发现

**Ditto 已领先的设计**：
1. **Kernel 零依赖** — 比 LEAN `Common/`（~100 文件）更纯粹，比 NautilusTrader `core/` 更轻量
2. **CQRS 四象限互斥** — 量化框架中无先例，超越了 Cosmic Python 的基本 CQRS 模式
3. **import-linter 强制边界** — 20 条契约机器执行，大多数开源项目仅靠人工审查
4. **表达式编译器** — 编译期优化 vs Qlib 运行时求值 vs panda_factor 运行时解析
5. **PIT 正确性内置** — 比 LEAN 手动配置更可靠，与 Databento 同理念

**Ditto 主要差距**：
1. **执行层单薄** — 仅 BacktestBrokerage，NautilusTrader 有 40+ Broker 适配器
2. **Engine/Analytics 平行隔离** — 限制了因子驱动策略（Qlib 将因子/模型/策略合为一体）
3. **单策略运行** — LEAN/NautilusTrader 支持多策略并发
4. **缺乏 backtest-live parity** — NautilusTrader 核心设计目标，Ditto 尚未规划实盘路径
5. **无统一数据模型** — Databento 的 live/historical 同 schema 设计，Ditto batch/stream 未统一

---

## 3. 审计方法

### 3.1 四维审查标准（每个模块）

| 维度 | 审查项 | 评分标准 |
|------|--------|---------|
| **架构** | 职责边界、内聚性、耦合度 | 单一职责 / 公共接口比例 / 传入耦合 |
| **抽象** | 领域建模、命名一致性、Protocol 恰当性 | DDD 建模规范 / 命名约定对照表 |
| **依赖** | importlinter 合规、隐式耦合、依赖方向 | 20 条契约全覆盖 / 无 TYPE_CHECKING 延迟导入 |
| **实践** | 代码风格、类型标注、错误处理、测试覆盖 | basedpyright strict / ruff / 80% 分支覆盖 |

### 3.2 发现严重程度

| 级别 | 定义 | 示例 |
|------|------|------|
| **P0** | 架构违规 / 数据正确性风险 | 循环依赖、数据泄漏、违反 importlinter 规则 |
| **P1** | 职责错位 / 抽象不当 | Service 包含 I/O 逻辑、Domain Model 有外部依赖 |
| **P2** | 命名不一致 / 风格偏离 | 同概念不同命名、混合中英文注释、类型标注缺失 |
| **P3** | 可改进但不紧急 | 优化建议、文档完善、测试补充 |

---

## 4. 审计执行计划（自底向上 6 Phase）

### Phase 1: Kernel + Infra（根基层）

#### Kernel 审查（11 文件，899 行）

**审查清单**：
- [ ] `__init__.py` 38 个符号的 flat re-export 是否合理？是否违反"re-export 链深度 ≤ 2"规则？
- [ ] Kernel 是否真正零行为（除 SimpleEventBus/SimulatedClock/RealtimeClock 薄实现）？
- [ ] 类型归属：`InstrumentId = NewType("InstrumentId", int)` 是否应该用更强类型？
- [ ] enums.py 中 8 个 StrEnum 是否都属于 Kernel？有没有应该下沉到具体包的？
- [ ] exceptions.py 中 `DataError` 命名在 Kernel 层是否恰当（暗示 Data 层概念）？
- [ ] quality.py 中 `L3CheckResult`/`ReconciliationResult` 是否属于 Kernel（来自 App CQRS 重构下沉）？
- [ ] specs.py 中 `DerivedSpec`/`MaterializationProfile` 是否与 Analytics 耦合过紧？
- [ ] math.py 单一函数 `pearson_correlation` 是否值得独立模块？
- [ ] research.py 中 4 个 frozen dataclass 是否真的被多包共享？
- [ ] Protocol 定义（Clock, EventBus）是否遵循"零实现"原则？

**业界对标**：
- LEAN `Common/` ~100 文件（过大），Ditto Kernel 11 文件（更纯粹）
- NautilusTrader `nautilus_model/` Rust 实现值对象（Price/Quantity/Money），更严格但语言绑定
- 最佳实践：Kernel 应只包含被 ≥3 个包使用的值对象和 Protocol

#### Infra 审查（48 文件，4,518 行）

**审查清单**：
- [ ] foundation/ vs services/ 的分层是否合理？services/notification 是否属于 infra？
- [ ] foundation/config/ 中的 `get_environment()` 是否被正确使用？
- [ ] observability/ 的 loguru/opentelemetry 集成是否泄漏到业务层？
- [ ] foundation/db/SQLitePool 是否与 Data 层的 SQLiteClient 重复？
- [ ] services/notification/ 模板是否包含业务逻辑？
- [ ] Infra 是否有隐式依赖 Data 或 Kernel 的代码？

**业界对标**：
- Hexagonal Architecture：Infra 应只实现 Domain 层定义的 Port
- NautilusTrader：`nautilus_network/` + `nautilus_serialization/` 是独立 crate，Infra 纯技术
- OpenBB：`openbb-core` 零 provider 依赖，Infra 微内核极简

---

### Phase 2: Data（最大包，重点审查）

#### Data 整体架构审查（325 文件，46,991 行 — 占总量 60%）

**宏观审查**：
- [ ] 11 个子模块的职责划分是否清晰？
- [ ] services/ vs storage/ vs sources/ 的三层架构是否一致执行？
- [ ] models/ 中 14 个文件是否有重复或交叉？
- [ ] di/ 中 11 个 Provider 是否与 services/ 的 Facade 一一对应？
- [ ] provider.py 的 DataProvider Protocol 是否是 Engine 的唯一窗口？

**services/ 子层审查**：
- [ ] 13 个 Facade Service 是否真正是 Facade（委托给 storage）？
- [ ] services/ports.py 的 Ports 模式是否一致使用？
- [ ] services/derived/ 中 9 个文件的职责划分
- [ ] services/metadata/ 与 storage/metadata/ 的边界
- [ ] services/trade/ 的 Facade + Writer 模式

**storage/ 子层审查**：
- [ ] CQRS Reader/Writer 分离是否一致执行？
- [ ] base/ 中的 parquet_store/sqlite_store 基类是否抽象得当？
- [ ] 存储层是否正确使用 polars（非 pandas）？
- [ ] 分区策略是否统一？

**sources/ 子层审查**：
- [ ] tushare/tdx/fred 三个适配器的架构是否一致？
- [ ] schemas/ 是否与 models/ 有重复？
- [ ] 数据源适配器是否正确隔离了外部 API 细节？

**quality/ 子层审查**：
- [ ] DQ 引擎的 checker 模式是否可扩展？
- [ ] 5 个 Protocol 定义是否都被正确使用？
- [ ] golden/ 与其他 checker 的关系

**关键命名审查**：
- [ ] Service 命名一致性（XxxService vs XxxFacade vs XxxManager）
- [ ] Reader/Writer 命名一致性
- [ ] Store vs Storage 命名区分
- [ ] Query 命名（BarQuery vs InstrumentQuery 在 provider.py，其他 Query 分散在各处）

**业界对标**：
- OpenBB TET 模式：Transform-Extract-Transform，标准模型 + Provider 实现 → Ditto sources/ 可借鉴
- Databento：统一 live/historical schema → Ditto batch/stream 数据模型统一
- Zipline DataPortal：统一读取门面 → Ditto DataProvider 是否足够？
- Qlib DataHandler：Processor chain + 表达式缓存 → Ditto data pipeline 管线设计
- daily_stock_analysis：多源 fallback 链 → Ditto sources 降级策略

---

### Phase 3: Analytics + Engine（平行域）

#### Analytics 审查（47 文件，8,204 行）

**审查清单**：
- [ ] expression/ 编译器管线（lexer→AST→parser→analyzer→codegen→compiler）是否清晰？
- [ ] factors/ 中 15 个因子模块的命名和分类是否合理？
- [ ] evaluation/ 与 factors/ 的边界
- [ ] materialization/ 的 contracts/models/planner 三层
- [ ] research/ 的域模型归属
- [ ] 对 data.errors 的依赖是否仅限于 DerivedError 系列？

**业界对标**：
- Qlib 表达式引擎：AST + LRU 缓存 + 2 级磁盘缓存 → Ditto 编译期优化是否足够？
- panda_factor：运行时 DSL 解析 vs Ditto 编译期 → 编译期更优但需验证缓存策略
- Zipline Pipeline：Factor/Filter/Classifier 三原语 + DAG → Ditto 的表达式是否覆盖相同语义？

#### Engine 审查（76 文件，12,085 行）

**审查清单**：
- [ ] alpha/ 的 Pipeline + Stage 模式是否与 LEAN Framework 对标？
- [ ] accounting/ 的领域模型是否纯粹（零 I/O）？
- [ ] execution/ 的 brokerage/planner/rules/targets 职责划分
- [ ] execution/reality/ 的仿真模型是否与 accounting 解耦？
- [ ] backtest/ 的引擎循环（EngineLoop）+ 10 steps 是否合理？
- [ ] portfolio/ 的 allocation/constraints/comparison 分工
- [ ] risk/ 的 pre_trade/post_trade 是否与 execution 正确交互？
- [ ] events.py 的 5 个事件是否覆盖了所有领域事件？
- [ ] 对 data.provider 的依赖是否严格通过 Protocol？

**业界对标**：
- LEAN 5 层 Framework：Universe→Alpha→Portfolio→Risk→Execution → Ditto 8 Stage 更细
- NautilusTrader：DDD 值对象（Price/Quantity/Money 定点整数），单线程内核，Component FSM → Ditto Engine 是否需要类似严格性？
- QSTrader：Alpha Model→Portfolio Construction→Order Sizer→Broker 简洁链路 → Ditto 是否过度复杂？

---

### Phase 4: App（编排层）

#### App 审查（95 文件，17,559 行）

**CQRS 合规性审查**：
- [ ] query/ 的 25+ Facade 是否全部只读？
- [ ] command/ 的 Command DTO + Handler 模式是否一致？
- [ ] process/ 的 4 个子域（ingestion/materialization/execution/quality）职责是否清晰？
- [ ] builders/ 是否只做运行时组装？
- [ ] R8 互斥规则在实际代码中是否被遵守（不仅 importlinter）？

**Process 复杂度审查**：
- [ ] process/ingestion/ 14 个文件 — 是否过度拆分？
- [ ] process/materialization/ 13 个文件 — 级联编排复杂度
- [ ] process/execution/ 14 个文件 — 回测/策略运行/因子桥接

**跨 CQRS 共享审查**：
- [ ] contracts.py 和 execution_dto.py 的共享 DTO 是否最小化？
- [ ] Provider 文件（6 个）是否正确注册所有依赖？

**业界对标**：
- Cosmic Python CQRS：Command 走 Domain Model，Query 走直接 DTO → Ditto 是否遵循？
- NautilusTrader NautilusKernel：中央编排器，所有组件初始化 + 生命周期管理 → Ditto App builders 对比

---

### Phase 5: Interfaces（边界层）

#### Interfaces 审查（109 文件，11,911 行）

**审查清单**：
- [ ] api/routes/ 14 个路由模块与 App query/command 的对应关系
- [ ] cli/commands/ 的命令与 App 层的映射
- [ ] jobs/flows/ 的 Prefect 集成是否泄漏业务逻辑？
- [ ] models/ 的 Pydantic 模型是否与 Data 层模型重复？
- [ ] registry/ 的 DI Composition Root 是否过于复杂？
- [ ] registry/contexts/ 的 Bundle 模式是否一致？
- [ ] services/ 已清空 — 是否有残留引用？
- [ ] interfaces-boundary 和 interfaces-service-isolation 规则是否被遵守？

**业界对标**：
- OpenBB：6 类 Plugin 扩展 + Router 命名空间树 → Ditto 的路由组织对比
- Databento：thin wrapper 哲学（零计算客户端）→ Interfaces 是否保持薄层？

---

### Phase 6: 跨切面审查

**错误体系审查**：
- [ ] Kernel DataError vs Data 层扩展异常的继承关系
- [ ] DerivedError 独立体系（不继承 DataError）是否合理？
- [ ] 异常命名一致性（Error vs Exception vs NotFound）
- [ ] 错误携带的 details dict 是否结构化？

**DI 体系审查**：
- [ ] Dishka Provider 注册是否一致？
- [ ] Composition Root 是否有遗漏？
- [ ] Ports 模式（data.services.ports）是否可推广？

**配置体系审查**：
- [ ] config/ 目录结构（development/testing/production）
- [ ] ENVIRONMENT vs DITTO_ENV 迁移状态
- [ ] Settings 类的层次结构

**测试体系审查**：
- [ ] 测试命名一致性
- [ ] 测试覆盖是否达到 80% 分支覆盖率？
- [ ] 集成测试 vs 单元测试的分层

---

## 5. 输出物

1. **目标架构蓝图** — 对照业界实践的理想状态 → `docs/reviews/2026-04-XX-target-architecture-blueprint.md`
2. **每模块审计报告** — 四维度评分 + 具体发现 → `docs/reviews/2026-04-XX-module-audit-<name>.md`
3. **发现清单** — P0-P3 排序的完整清单 → `docs/reviews/2026-04-XX-audit-findings.md`
4. **逐模块修复计划** — 具体改进步骤 → `docs/plans/2026-04-XX-<module>-fix-plan.md`

---

## 6. 执行方式：边审边讨论

每个 Phase 的执行流程：

1. **深入扫描** — 并行启动 Explore Agent 读取模块内所有关键文件
2. **四维审查** — 按审查清单逐条检查，记录发现
3. **实时讨论** — 向用户呈现本 Phase 的发现清单，讨论严重程度和修复方向
4. **记录报告** — 将确认的发现写入审计报告
5. **下一 Phase** — 用户确认后继续

Phase 间可随时暂停、回溯或调整审计标准。

---

## 7. 验证方式

- 每个 Phase 完成后运行 `pixi run -e dev arch-check` 验证依赖约束
- 发现 P0 级别问题时立即标记
- 审计过程中不修改代码，仅记录发现
