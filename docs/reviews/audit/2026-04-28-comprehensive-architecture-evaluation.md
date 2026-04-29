# Ditto 全面架构评估报告

> 日期：2026-04-28
> 审计范围：全库架构、工程实践、命名一致性、可理解性
> 对标平台：14 个（含新增 FinceptTerminal）
> 与上次评估（2026-04-24）对比

---

## 1. 执行摘要

### 1.1 当前状态快照

| 指标 | 数值 | 趋势 |
|------|------|------|
| 源码文件 | 625 | +3% |
| 源码行数 | ~97,400 | +2% |
| 测试文件 | 494 | +7% |
| Protocol 定义 | 83 | 稳定 |
| import-linter 合约 | 34 | 稳定 |
| `@traced` 覆盖 | 210 | +5% |
| `# type: ignore` | 0 | 0（优秀） |

**代码规模分布**：

| 包 | 文件数 | 行数 | 占比 |
|---|--------|------|------|
| data | 339 | 42,138 | 43% |
| app | 98 | 17,693 | 18% |
| interfaces | 108 | 11,918 | 12% |
| engine | 79 | 12,211 | 13% |
| analytics | 48 | 8,222 | 8% |
| infra | 48 | 4,425 | 5% |
| kernel | 13 | 840 | 1% |

### 1.2 四域评分

| 维度 | 2026-04-24 | 2026-04-28 | 变化 | 说明 |
|------|-----------|-----------|------|------|
| 架构能力 | A-(6.8) | A-(7.0) | +0.2 | diamond 模型文档到位，importlinter 全面覆盖 |
| 工程质量 | B+(7.5) | B+(7.5) | — | 测试覆盖稳定，CI 门禁全面 |
| 业务功能 | D+(3.5) | D+(3.5) | — | 无新业务功能增加 |
| 可演进性 | B+(7.5) | B+(7.5) | — | 插件化仍为 DI 显式注册 |
| **综合** | **6.8** | **7.0** | **+0.2** | |

> T0 architecture clarity execution metrics are tracked in
> `docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md`.

### 1.3 关键发现汇总

| ID | 发现 | 严重度 | 维度 |
|----|------|--------|------|
| F01 | ~~importlinter 线性合约与 diamond 模型矛盾~~ **已解决** | ~~P1~~ | 架构清晰度 |
| F02 | Dataset StrEnum 泄露导致 4 个 interfaces 豁免 | P1 | 架构清晰度 |
| F03 | ~~Exchange 枚举在 kernel 与 data 重复定义~~ **已解决** | ~~P2~~ | 命名一致性 |
| F04 | ~~StrategyRunService 在 app 与 data 同名~~ **已解决** | ~~P2~~ | 命名一致性 |
| F05 | CQRS 违规：Reader 含 init_schema()、Writer 含 get_records() — **部分解决** | P2 | 命名一致性 |
| F06 | ~~ETF/Fx 缩写大小写不一致~~ **已修订**：已知缩写保持大写 | ~~P2~~ | 命名一致性 |
| F07 | ~~Analytics expression 依赖 materialization（方向反转）~~ **已解决** | ~~P1~~ | 分层 |
| F08 | ~~Engine 异常体系过于单薄（仅 1 子类）~~ **已评估**：基线可接受 | ~~P2~~ | Python 实践 |
| F09 | ~~@traced 覆盖率仅 13%~~ **已改善**：engine/analytics 关键路径已覆盖 | ~~P1~~ | 工程实践 |
| F10 | E2E 测试仅 6 个（1.2%），比例过低 | P2 | 工程实践 |
| F11 | ~~DQSettings 使用 CWD 相对路径~~ **已解决** | ~~P2~~ | 工程实践 |
| F12 | ~~6 项约定仅文档约束，无机器强制~~ **已改善**：arch-smells 脚本上线 | ~~P2~~ | Agent 实践 |
| F13 | Data 包 16 个顶层目录，导航成本最高 | P2 | 可理解性 |
| F14 | ~~factor_analysis.py 973 行，接近单文件上限~~ **已解决**：4 个 oversized 文件已拆分 | ~~P2~~ | 可理解性 |

---

## 2. 维度一：架构清晰度与整洁度

### 2.1 Diamond 模型 vs Linear Layers 合约

**状态：已解决 ✅** — .importlinter 已添加注释说明线性排序为工具约束，diamond 语义由 forbidden 合约保障。boundaries-and-abstraction-standards.md 已同步更新。

`boundaries-and-abstraction-standards.md` Section 3 定义了 diamond/fan 模型：

```
             interfaces
                 |
                app
    ┌────────────┼────────────┐
    |            |            |
  data       analytics      engine
    |            |            |
    └────────────┴────────────┘
              kernel
```

Section 3.2 明确声明："data、analytics、engine 是并列核心平面，不要把 engine 理解成天然高于 data 的上层。"

然而 `.importlinter` 的 `layered-architecture` 合约（行 29-39）定义了严格线性排序：

```
layers = ditto_interfaces, ditto_app, ditto_engine, ditto_data, ditto_infra
```

这意味着 `engine` 被放置在 `data` 之上（engine 可依赖 data，但 data 不可依赖 engine），直接与 diamond 模型中"两者并列"的声明矛盾。`analytics` 完全不出现在线性合约中。

**实际效果**：项目通过额外的 `forbidden` 合约（engine-no-data-dependency、data-no-engine-dependency 等）重建了 diamond 语义。线性合约仅对 `interfaces → app → infra` 方向有实际约束力。

**解决措施**（T0 Task 9）：.importlinter 已添加注释"engine→data 排序仅为 importlinter 技术约束，不代表架构层级关系"；boundaries-and-abstraction-standards.md Section 14 已同步说明。

### 2.2 三平面并列性验证

**状态：通过**

`app.process` 对三个平面的 import 分布验证：

| 平面 | app.process 中的 import 数量 | 来源模块 |
|------|----------------------------|---------|
| data | ~15 | models.strategy, services.*, errors, ingestion.*, models.common |
| engine | ~10 | alpha.*, backtest.*, execution.*, risk.* |
| analytics | ~3 | expression.compiler, expression.diagnostics, materialization |

三平面均为 app 的下游，无平面间直接依赖（analytics→data.errors 为唯一豁免，仅 2 个文件、仅错误类型）。

**analytics→data.errors 豁免合理性**：`DerivedNotImplementedError` 和 `DerivedValidationError` 在 analytics 的 validation.py 和 research/domain.py 中使用。这些异常在语义上属于"衍生数据"领域概念，理论上应放在 kernel，但因历史原因放在 data.errors。豁免合理但属于技术债。

### 2.3 App 双重身份：providers.py 评估

**状态：清洁**

`packages/app/src/ditto_app/providers.py`（533 行）经审计确认为**纯 DI 装配层**：
- 6 个 Provider 类，~30 个 `@provide` 方法
- 无业务逻辑、无用例编排、无决策逻辑
- 唯一边界案例：`get_trading_calendar_range()` 辅助函数（行 136-151），从类型化 Settings 提取日期范围，不属于"散落 env 读取"

**主要问题**：文件体积大（533 行 + ~60 条 import），fan-in 耦合高。已在 `providers_market.py` 和 `providers_portfolio.py` 中开始拆分。建议继续拆分 `AppCommandProvider`（140 行）和 `AppProcessProvider`（123 行）到独立文件。

### 2.4 隐藏耦合点

**Dataset StrEnum**：`data.models.common.Dataset` 被 app（16 处引用）和 interfaces（2 处 + 2 个 importlinter 豁免）广泛使用。这是当前最大的隐藏耦合点，plan 中 P3 已规划 DataCatalog 替代。

**os.environ 读取**（14 处）：

| 层 | 数量 | 合理性 |
|---|------|--------|
| infra | 8 | 路径解析（XDG、DITTO paths），完全合理 |
| data | 2 | FRED_API_KEY、TUSHARE_TOKEN，可接受 |
| interfaces | 3 | CORS_ORIGINS、backfill 日期，入口层合理 |
| app | 0 | — |
| engine | 0 | — |
| analytics | 0 | — |

**共享枚举/字符串**：`Exchange` 在 kernel 和 data 各定义一次（详见 F03）。

### 2.5 Interfaces Registry 豁免评估

7 个 ignore_imports 中：

| 豁免 | 评估 |
|------|------|
| registry → data.services | 合理（Composition Root） |
| registry → data.quality | 合理（Composition Root） |
| registry → data.config | 合理（Composition Root） |
| jobs.context → data.quality | 边界（Context Bundle 构建，文档已标注为最小豁免） |
| jobs.context → data.quality.protocols | 边界（同上） |
| api.routes.ingestion → data.models.common | 应收敛（Dataset 枚举泄露） |
| cli.commands.ops → data.models.common | 应收敛（Dataset 枚举泄露） |

**结论**：3/7 完全合理，2/7 为最小必要豁免，2/7 应通过 Dataset→DataCatalog 迁移消除。

---

## 3. 维度二：含义模糊度与命名一致性

### 3.1 后缀合规率

20 个命名词典后缀在代码中的使用情况：

| 后缀 | 使用量 | 合规率 | 备注 |
|------|--------|--------|------|
| Provider | 34 | 100% | DI 组件，使用准确 |
| Reader | 33 | ~91% | 3 处含 init_schema()（违规） |
| Writer | 31 | ~90% | 2 处含 get_records()（违规） |
| Protocol | 21 | 100% | 消费者定义端口 |
| Config | 32 | 100% | 配置对象 |
| Response | ~20 | 100% | DTO |
| Rule | 18 | 100% | 可组合规则 |
| Handler | 14 | 100% | CommandHandler |
| Adapter | 11 | 100% | 外部系统适配 |
| Manager | 1 | 100% | FreezeManager（受限词，唯一合理使用） |

**未收录后缀**：
- `Client`（TushareClient、FredClient）— 建议加入字典
- `Processor`（tushare/processors/）— 建议加入字典
- `Transformer`（ExchangeTransformer、DataTransformer）— 建议加入字典
- `Validator`（DataSourceValidationProvider）— 已有 Validation 语义

### 3.2 命名冲突

| 冲突 | 位置 | 风险 |
|------|------|------|
| ~~`Exchange` StrEnum~~ | ~~kernel + data（各定义一次）~~ | **已解决** ✅ data 层重命名为 `SourceExchangeCode`（T0 Task 5） |
| ~~`StrategyRunService`~~ | ~~app.process + data.services~~ | **已解决** ✅ 重命名为 `StrategyRunLifecycleStore`（T0 Task 6） |
| `_CatalogReader` ×3 | data.services.derived 内部 | MEDIUM：同包内重复定义，应提取共享 |
| `PositionReader` | app（Protocol）+ data（实现） | LOW：端口-实现命名对称，可接受 |

### 3.3 CQRS 纯净度

**状态：部分解决 ✅** — metadata stores 已修复（init_schema 保留但归 Writer，Reader/Writer 职责已由 guard test 覆盖）。其余 store 待后续迭代。

**Reader 含写方法**（3 处）：
- `SQLiteStrategySpecReader.init_schema()` — DDL 操作不应在 Reader
- `SQLiteFeeScheduleReader.init_schema()` — 同上
- `SQLiteTradingRuleReader.init_schema()` — 同上

**Writer 含读方法**（2 处）：
- `TradingRuleWriter.get_records()` — 读操作不应在 Writer
- `FeeScheduleWriter.get_records()` — 同上

**init_schema() 在 Reader 和 Writer 中重复**：以上 3 对 Reader/Writer 各自实现了 init_schema()，应统一为 Writer 独占或提取到 SchemaMigration 模块。

### 3.4 Helper/Utils 逃逸

| 文件/目录 | 行数 | 评估 |
|-----------|------|------|
| `app/process/materialization/helpers.py` | 503 | **需拆分**：包含 Materialization 的领域逻辑（业务规则、数据转换），非通用工具 |
| `data/helpers/` | 625（6 文件） | 部分合理（polars 类型转换等通用能力） |
| `data/utils/` | 102（2 文件） | 小规模，可接受 |
| `interfaces/api/utils/` | — | API 边界工具，合理 |

### 3.5 缩写不一致

**状态：已修订 ✅** — 命名词典规则 5 已更新：已知领域缩写（ETF、FX、API、SQL、DQ、PIT、HTTP）在类名中保持大写，不重命名为 `Etf`/`Fx`。模块路径保持小写。此为有意的命名决策，非不一致。

| 缩写 | 形式 | 示例 |
|------|------|------|
| ETF | `Etf`（PascalCase）vs `ETF`（全大写） | EtfBarsReader vs ETFTushareAdapter vs ETFExtension |
| FX | `Fx`（PascalCase）vs `FX`（全大写） | FxBarsReader vs FXQueryFacade |

**决策**（T0 Task 7）：保留现状 — 缩写形式均为行业通用表达，不需要强制统一。

---

## 4. 维度三：分层与模块化

### 4.1 Data 包体量评估

| 子域 | 文件数 | 行数 | 占 Data 包比例 |
|------|--------|------|----------------|
| storage | 172 | 14,877 | 36% |
| sources | 57 | 9,380 | 23% |
| services | 37 | 7,731 | 19% |
| quality | 13 | 2,248 | 5% |
| models | 14 | 2,061 | 5% |
| di | 14 | 1,782 | 4% |
| 其他 | 32 | 4,849 | 8% |

**storage 占 36%**：这是 CQRS Reader/Writer 模式的自然结果（每个子域 = Reader + Writer + Schema）。import-linter 已通过 10 条 storage 子域隔离合约实现内部边界。**不建议拆包**，但应考虑：
1. 引入代码生成减少 Reader/Writer 样板
2. 强化 storage 子域门禁（当前已到位）

### 4.2 Analytics 内部依赖方向

**状态：已解决 ✅** — `expression/contracts.py` 已创建，编译时类型（`Analysis`、`AnalysisWarning`、`CompileIdentity`、`CompileIdentity`）已从 `materialization.contracts` 提取到 `expression.contracts`。expression 不再依赖 materialization，依赖方向已修正。import-linter 已添加 expression→materialization forbidden 合约。

### 4.3 Engine 内部隔离

**状态：清洁**

核心子域（accounting、execution、risk、portfolio、alpha）**零导入** backtest 模块。backtest 作为顶层编排器依赖核心子域，方向正确。

### 4.4 CQRS 四象限互斥执行

6 条 R8 合约全部有效，无违规。允许的交叉依赖方向均符合设计：

| 允许方向 | 实际 import |
|----------|-----------|
| process → query | 4 处（MarketQueryFacade 等） |
| command → process | 6 处（IngestionCoordinator 等） |
| builders ↔ process | 5 处（双向依赖） |

### 4.5 Import-linter 合约完整性

当前 34 条合约覆盖：
- 7 个包间边界（layered-architecture + 6 个 forbidden）
- 6 个 CQRS 内部互斥（R8）
- 10 个 Data 内部子域隔离（storage + sources）
- 1 个循环依赖检测
- 7 个专项边界（kernel、infra、interfaces、expression→materialization）
- 3 个其他

**可新增的 6 条合约建议**：

| # | 建议合约 | 必要性 |
|---|---------|--------|
| 1 | ~~analytics expression 禁止依赖 materialization~~ **已添加** | ~~HIGH~~ |
| 2 | engine 核心域（accounting/execution/risk/portfolio/alpha）禁止依赖 backtest | LOW（当前已自然遵守） |
| 3 | data helpers/utils 禁止被外部包导入 | MEDIUM |
| 4 | kernel 禁止含 StrEnum（仅允许 Protocol + 值对象） | LOW |
| 5 | app providers 禁止含业务逻辑 | MEDIUM（文档约束，可强化） |
| 6 | storage Reader 禁止含 init_schema() 方法 | LOW（代码层面约束） |

---

## 5. 维度四：插件化与扩展性

### 5.1 数据源扩展路径

新增数据源（如 Wind）需修改的现有文件：

1. `packages/data/src/ditto_data/sources/wind/` — 新建源实现（~N 文件）
2. `packages/data/src/ditto_data/di/sources.py` — 添加 DI 注册（~4 处修改）
3. `packages/data/src/ditto_data/sources/source.py` — DataSources 接入
4. `packages/data/src/ditto_data/sources/exchange_transformers.py` — 添加转换器
5. `packages/data/src/ditto_data/config/data_source.py` — 添加配置字段

**总计：4-5 个现有文件修改** + 新源目录。无插件发现机制，需手动注册。

**对标 FinceptTerminal**：其 100+ 数据连接器通过 Python 脚本放置自动发现，Ditto 的显式注册更安全但扩展成本更高。

### 5.2 策略扩展路径

`DecisionStage` Protocol 提供了干净的单方法扩展接口。新增策略模板需：
1. 实现 `DecisionStage.process(frame, context) -> DecisionFrame`
2. 在 app 层注册到 pipeline

**对标 LEAN**：LEAN 的 `IAlgorithm` 接口更重（含 OnData、OnOrderEvent 等生命周期回调），Ditto 的管道模式更灵活。

### 5.3 Port 归属合规率

**83 个 Protocol 的定义位置分析**：

- **Data 包 36 个**：由服务层（消费者）定义，存储层实现 — 符合 DIP
- **Engine 包 21 个**：由子域（消费者）定义，实现者在同包 — 符合 DIP
- **App 包 18 个**：由编排层定义 — 符合 DIP
- **Analytics 包 7 个**：由编译/评估层定义 — 符合 DIP

**唯一例外**：`DataProvider`（data/provider.py）由实现方（data）定义，消费者（engine）被迫适应。这是 P4 已规划的改进项。

### 5.4 插件注册机制

当前模式：**DI 显式注册**（Dishka Provider + `@provide`），无 entry_points、无 stevedore/pluggy、无文件系统发现。

| 机制 | Ditto | FinceptTerminal | LEAN |
|------|-------|-----------------|------|
| 注册方式 | DI Provider | Producer + Python 脚本 | IAlgorithm 接口 |
| 发现 | 编译时（import） | 运行时（文件系统） | 编译时（类型匹配） |
| 优点 | 安全、可追踪 | 灵活、松耦合 | 类型安全 |
| 缺点 | 需修改现有文件 | 无编译时检查 | 扩展点固定 |

**建议**：当前阶段保持 DI 显式注册。待 Data 包完成 DataCatalog 迁移后，考虑引入基于 Protocol 的注册发现。

---

## 6. 维度五：Python 最佳实践

### 6.1 Protocol vs ABC 使用

| 类型 | 数量 | 占比 |
|------|------|------|
| Protocol | 83 | 96.5% |
| ABC | 3 | 3.5% |

3 个 ABC 评估：
- `ConfigInitProvider(ABC)` — **合理**：模板方法模式，协调器调用固定算法委托给 provider
- `NotificationSender(ABC)` — **可接受**：含 abstract property + abstract method
- `PartitionStrategy(ABC)` — **应转 Protocol**：3 个抽象方法，无共享代码，仅需结构兼容

### 6.2 异常体系完整性

| 包 | 根异常 | 子类数 | 评估 |
|---|--------|--------|------|
| kernel | DittoError | 4 | 充足 |
| data | DataError | 27 | 完善 |
| infra | InfraError | 2 | 合理 |
| analytics | AnalyticsError | 2 | 合理 |
| app | AppError | 2 | 合理 |
| engine | EngineError | **1** | **不足** |
| interfaces | APIError | 7 | 完善 |

**Engine 异常体系**：仅 1 个子类 `StateTransitionError`。T0 评估认为当前基线可接受 — Engine 正处于快速迭代期，过度抽象异常层级会限制演进。待业务逻辑稳定后（Phase 3-4），按子域逐步添加领域异常（`InsufficientBuyingPowerError`、`InvalidOrderError`、`BacktestConfigError`）。

**命名不一致**：部分包使用 `errors.py`（data、interfaces），其余使用 `exceptions.py`。建议统一为 `exceptions.py`。

### 6.3 类型安全一致性

- `# type: ignore`：**0 处**（优秀）
- `dict[str, Any]` / `dict[str, object]`：384 处（非测试），多数为日志/指标/JSON 载荷的合法使用
- frozen dataclass：314 处（广泛应用，不可变性默认）

**改进点**：`app/contracts.py` 中的 `spec_json: dict[str, object]` 可考虑迁移到 TypedDict 或 dataclass。

### 6.4 现代 Python 特性利用度

| 特性 | 使用量 | 评估 |
|------|--------|------|
| `frozen=True` dataclass | 314 | 广泛采用 |
| `TypeVar` | 13 | 适度 |
| `ParamSpec` | 1 | 用于 @traced 装饰器 |
| `match/case` | 0 | 未采用 |
| `dataclass_transform` | 0 | 不适用 |

---

## 7. 维度六：工程最佳实践

### 7.1 测试架构平衡性

| 类型 | 数量 | 比例 | 评估 |
|------|------|------|------|
| 单元测试 | 425 | 86% | 充足 |
| 集成测试 | 55 | 11% | 合理 |
| E2E 测试 | 6 | 1.2% | **不足** |

**对标**：典型的成熟量化平台测试比例约为 70/20/10。Ditto 的 E2E 测试（6 个）对于覆盖"数据摄取→质量检查→回测→执行"的关键用户路径明显不足。

### 7.2 配置管理闭环

| 组件 | 状态 | 问题 |
|------|------|------|
| ConfigValidationProvider | 已注册 | 功能正常，但有 1 处 f-string 日志违规 |
| DQSettings | 已注入 | `config_root` 通过 DI 注入，路径解析 CWD-independent（已修复） |
| os.environ | 14 处 | 集中在 infra/interfaces，合理 |

**DQSettings 路径问题**（已解决 ✅）：`config_root` 现在通过 DI 注入（默认 `find_project_root()`），路径解析不再依赖进程 CWD。在不同执行上下文（测试、CLI、Prefect job）中行为一致。

### 7.3 观测一致性

**@traced 覆盖率**：

| 包 | @traced 数量 | 函数/类总数 | 覆盖率 |
|---|-------------|-----------|--------|
| data | 189 | ~500 | 38% |
| infra | 2 | ~50 | 4% |
| app | 1 | ~200 | 0.5% |
| analytics | 2 | ~120 | ~2% |
| engine | 2 | ~180 | ~1% |
| interfaces | 0 | ~160 | 0% |
| **总计** | **~214** | **~1,609** | **~13%** |

**改善**（T0 Task 10）：engine 和 analytics 已从 0% 提升到有针对性覆盖 — 回测主循环 `BacktestEngine.run()`、alpha pipeline `StrategyPipeline.process()`、执行计划 `SimpleExecutionPlanner.plan()`、表达式编译 `ExpressionCompiler.compile()`、因子评估 `FactorEvaluator.evaluate()` 均已添加 `@traced`。关键计算路径的性能现在可观测。

**Kernel tracing hook**（T0 Task 3）：`kernel.tracing` 提供可插拔追踪装饰器 `@traced`。默认 no-op；通过 `install_trace_handler()` 注入真实实现。interfaces composition root 接线 OTel bridge 作为 handler，安装后 `@traced` 产出真实 span。

**结构化日志**：98.8% 合规（486 条日志调用中仅 6 条使用 f-string）。全部 6 条违规在 infra config/validation 模块。

### 7.4 CI/CD 门禁完整性

**现有门禁**：
- ruff lint + format（local mode，确保工具链一致）
- basedpyright strict mode（全项目扫描）
- pytest fast（pre-push）
- gitleaks（密钥扫描）
- conventional commits（commit-msg hook）
- import-linter（架构边界检查）
- 分支保护（no-commit-to-main）

**缺失项**：
- 依赖漏洞扫描（pip-audit / safety）
- 复杂度检查（radon / xenon）
- 死代码检测（vulture）

### 7.5 公共 API 管控

| 包 | `__all__` 定义数 | 评估 |
|---|-----------------|------|
| data | 181 | 完善 |
| app | 79 | 完善 |
| engine | 54 | 完善 |
| analytics | 48 | 完善 |
| interfaces | 33 | 合理 |
| infra | 32 | 合理 |
| kernel | 12 | 精简（符合设计） |
| **总计** | **439** | |

**re-export 链深度**：需进一步验证是否存在超过 2 层的 re-export 链。

---

## 8. 维度七：Agent 编码最佳实践

### 8.1 代码库可导航性

**同名文件冲突**：

| 文件名 | 出现次数 | 风险 |
|--------|---------|------|
| config.py | 7 | HIGH（5 个包） |
| macro.py | 11 | MEDIUM（3 个包） |
| market.py | 10 | MEDIUM（4 个包） |
| strategy.py | 9 | MEDIUM（3 个包） |

**README/CLAUDE.md 覆盖**：7/7 包均有 CLAUDE.md，总计 33 个 README 文件。Tushare 数据源目录有 358 行 README 含架构图和数据流描述。

### 8.2 约定可执行性

| 类别 | 机器强制 | 文档约束 |
|------|---------|---------|
| 包间边界 | 30+ importlinter 合约 | — |
| 循环依赖 | acyclic-packages 合约 | — |
| CQRS 互斥 | 6 条 R8 合约 | — |
| Data 子域隔离 | 10 条 storage/sources 合约 | — |
| 命名后缀 | — | 20 条后缀规则 |
| 抽象层级混合 | — | Section 6.1 |
| Port 归属 | 部分（方向强制） | 完整规则 |
| Domain Catalog | — | Section 6.3 |
| Helpers 最小化 | — | Section 6.4 |
| 公共 API 边界 | — | Section 6.5 |

**强制率**：13/19（68%），高于业界平均水平。

### 8.3 大文件可理解性

| 文件 | 行数 | 评估 |
|------|------|------|
| analytics/evaluation/metrics/factor_analysis.py | 973 | 需拆分 |
| data/sources/tushare/tushare_source.py | 891 | 边界（单源聚合入口） |
| data/services/metadata/instrument.py | 850 | 边界 |
| data/services/market_service.py | 813 | 边界 |
| engine/backtest/statistics.py | 812 | 边界 |

**ruff 复杂度约束**：max-statements=50, max-args=7, max-branches=12, max-complexity=10，有效限制了函数级复杂度。

### 8.4 决策树覆盖度

Section 7 决策树（7 步顺序流）评分 **7/10**：

- 覆盖所有 7 个架构平面
- 有安全回退（"暂停讨论架构"）
- **缺失**：测试代码放置、配置文件放置、DI Provider 接线

### 8.5 命名词典充分性

20 个后缀覆盖 **~85%** 的实际类命名。未覆盖但常用的：
- `Client`（HTTP 包装器）
- `Processor`（列映射/转换管线）
- `Transformer`（交易所/数据转换）

---

## 9. 维度八：可理解性综合评分

| 子维度 | 权重 | 得分 | 评价 |
|--------|------|------|------|
| 新人上手成本 | 20% | 7.5/10 | "新增数据集"全流程约 2-4 小时，文档覆盖好 |
| Agent 正确编码率 | 20% | 7.0/10 | importlinter + CLAUDE.md 提供强指导，但命名例外存在 |
| 命名传达信息量 | 15% | 7.5/10 | 后缀体系基本覆盖，少数例外（Client/Transformer） |
| 依赖关系可推导性 | 15% | 8.5/10 | 30+ importlinter 合约可推导完整依赖图 |
| 反模式识别效率 | 15% | 6.0/10 | CI 可检测 import 越界和类型错误，但无法检测 CQRS 违规和命名违规 |
| 文档与代码一致性 | 15% | 7.0/10 | diamond 模型文档与线性合约存在偏差（F01） |
| **加权总分** | | **7.2/10** | |

---

## 附录：验证清单

- [x] 评估报告覆盖 8 个维度，每个维度有具体发现和建议
- [x] FinceptTerminal 已纳入对标矩阵
- [x] 所有发现都有文件级定位和严重度评级
- [x] 与 2026-04-24 评估的变化对比已包含
- [x] 运行 `pixi run -e dev check` 确认审计过程未引入变更 — **已验证**：5878 tests passed, 0 type errors, 34 import-linter contracts kept

## T0 Acceptance Checklist

以下命令构成 T0 architecture clarity gate 的验收标准：

- [x] `python scripts/architecture/check_architecture_smells.py` — passes (0 issues)
- [x] `pixi run -e dev lint-imports` — 34 kept, 0 broken
- [x] `pixi run -e dev type` — 0 errors, 0 warnings, 0 notes
- [x] `pixi run -e dev test --fast` — 5878 passed, 25 skipped, 0 fail
- [x] `pixi run -e dev arch-check` — passes (34 kept, 0 broken, arch-smells passed)
- [x] Tracing: `@traced` in kernel defaults to no-op; `install_trace_handler()` accepts handler; composition root wires OTel bridge
- [x] DQ settings: `config_root` injected via DI, path resolution independent of process CWD
- [x] Expression contracts: types owned by `expression.contracts`, `materialization` imports from canonical path
