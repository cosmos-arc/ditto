# Ditto 全面架构审计与 T0 差距分析计划

## Context

Ditto 是一个 A 股 ETF 量化投资平台，当前评分 6.8/10，架构能力 A- 但业务功能 D+。2026-04-24 审计后已进入"架构骨架基本可靠、局部债务影响演进速度"阶段。本次审计旨在：

1. **全面评估报告**：以 8 个维度系统性审计 `boundaries-and-abstraction-standards.md` 及整体架构，对标业界最新最佳实践（含新增 FinceptTerminal）
2. **T0 差距分析与设计**：从世界级标准出发，识别关键差距并产出可执行的设计方案

## 对标产品矩阵（14 个平台）

| 平台 | 语言 | 定位 | 对标维度 |
|------|------|------|---------|
| QuantConnect LEAN | C#/Python | 全栈量化平台 | 策略生命周期、组合模型、brokerage |
| NautilusTrader | Rust/Python | 高性能交易 | DDD、事件驱动、backtest/live 一致性、状态机 |
| Microsoft Qlib | Python | AI 量化研究 | 因子研究、ML 集成、数据管理 |
| Zipline | Python | 回测框架 | DataPortal、Pipeline API |
| VectorBT | Python | 向量化回测 | 性能优化、NumPy 集成 |
| Backtrader | Python | 回测框架 | Strategy/Cerebro 模式 |
| OpenBB | Python | 金融数据终端 | 数据源架构、TET pipeline |
| Databento | C++/Python | 市场数据 | 高性能数据处理 |
| Panda QuantFlow | Python | 因子平台 | 因子管理、表达式语言 |
| Panda Factor | Python | 因子平台 | 因子计算、组合优化 |
| FinceptTerminal | C++/Python | 金融终端 | DataHub pub/sub、数据源覆盖广度、MCP 集成 |
| Django | Python | Web 框架 | 分层架构、插件系统（参考工程最佳实践） |
| FastAPI | Python | API 框架 | 依赖注入、类型安全（项目已使用） |
| pytest | Python | 测试框架 | 插件架构、fixture 系统（参考可测试性） |

---

## Phase 1: 交付物一 — 全面架构评估报告

产出文件：`docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`

### 报告结构

#### 1. 执行摘要

- 当前状态快照（代码规模、质量指标、测试覆盖）
- 四域评分（架构/工程/业务/可演进性）
- 与 2026-04-24 评估的变化对比
- 关键发现汇总表（P0/P1/P2 分级）

#### 2. 维度一：架构清晰度与整洁度

**审计项**：

| # | 审计项 | 方法 | 严重度标准 |
|---|--------|------|-----------|
| 2.1 | 心智模型一致性：diamond 模型 vs linear layers contract 是否矛盾 | 对比 `boundaries-and-abstraction-standards.md` Section 3 与 `.importlinter` layered-architecture contract | HIGH: 文档与执行模型矛盾 |
| 2.2 | 三平面并列性验证：data/analytics/engine 是否真正并列 | 统计 app.process 对三个平面的 import 分布，检查 analytics→data.errors 是否构成隐式上下游 | MEDIUM: 隐式方向 |
| 2.3 | App 双重身份冲突：use case 编排 vs composition root vs provider 聚合 | 检查 app/providers.py(533行) 的职责边界 | HIGH: 编排与装配混合 |
| 2.4 | 隐藏耦合点：Dataset StrEnum、os.environ 读取、共享文件路径 | grep 所有跨包共享的 enum/string/env/path 约定 | HIGH: 未被门禁覆盖的耦合 |
| 2.5 | interfaces/registry 豁免合理性：10 个 ignore_imports 是否可收敛 | 逐一评估每个豁免的必要性 | MEDIUM: 豁免膨胀 |

**关键文件**：
- `docs/architecture/boundaries-and-abstraction-standards.md`（Section 3）
- `.importlinter`（27 条合约）
- `packages/app/src/ditto_app/providers.py`
- `packages/data/src/ditto_data/models/common.py`
- `interfaces/src/ditto_interfaces/registry/container.py`

#### 3. 维度二：含义模糊度与命名一致性

**审计项**：

| # | 审计项 | 方法 |
|---|--------|------|
| 3.1 | 后缀合规率：20 个后缀定义 vs 实际使用的偏差 | 遍历所有 class 定义，按命名词典分类 |
| 3.2 | 命名冲突：PositionReader、_CatalogReader×3、StrategyRunService 等 | 列出所有跨包同名符号及消歧方案 |
| 3.3 | CQRS 纯净度：Writer 含读方法(8处)、Reader 含写方法(3处) | grep storage/ 下的 get_checksum/init_schema 泄漏 |
| 3.4 | Helper/Utils 逃逸：503 行的 helpers.py | 评估所有 helpers/utils 目录是否符合 Section 6.4 |
| 3.5 | 缩写不一致：Etf/etf、FX/Fx/Fx 等 | 搜索大小写混用的标识符 |

**关键文件**：
- `packages/data/src/ditto_data/storage/`（109 个 reader/writer 文件）
- `packages/app/src/ditto_app/process/materialization/helpers.py`（503 行）
- `packages/data/src/ditto_data/services/derived/`（_CatalogReader ×3）

#### 4. 维度三：分层与模块化

**审计项**：

| # | 审计项 | 方法 |
|---|--------|------|
| 4.1 | Data 包体量评估：340 文件 / 42,343 行(43%)是否应拆分 | 按子域统计行数、跨子域依赖、外部消费者 |
| 4.2 | Analytics 内部依赖方向：expression→materialization 反转 | 验证 `expression/analyzer.py` 对 `materialization/contracts.py` 的 import |
| 4.3 | Engine 内部隔离：核心子域 vs backtest runtime | 检查 accounting/execution/risk/portfolio/alpha 是否依赖 backtest |
| 4.4 | CQRS 四象限互斥执行情况 | 验证 R8 6 条合约的实际隔离效果 |
| 4.5 | Import-linter 合约完整性：Section 10 建议的 6 条新合约 | 逐一评估必要性和可行性 |

**关键文件**：
- `.importlinter`（27 条现有 + 6 条建议）
- `packages/analytics/src/ditto_analytics/expression/analyzer.py`
- `packages/engine/src/ditto_engine/`（检查核心→runtime 方向）
- `packages/app/src/ditto_app/`（CQRS 四象限）

#### 5. 维度四：插件化与扩展性

**审计项**：

| # | 审计项 | 方法 |
|---|--------|------|
| 5.1 | 数据源扩展路径：新增数据源需改多少文件 | 走一遍 Section 8.2 playbook |
| 5.2 | 策略扩展路径：新增策略模板需改多少文件 | 走一遍 DecisionStage + StrategyPipeline 扩展 |
| 5.3 | Port 归属合规率：多少 Protocol 由消费者定义 vs 实现方定义 | 遍历 109 个 Protocol 的定义位置 vs 使用位置 |
| 5.4 | 插件注册机制：entry_points vs 手动注册 vs DI | 对比 FinceptTerminal Producer 模式、pytest 插件模式 |

**对比 FinceptTerminal**：
- DataHub pub/sub 模式（topic-based addressing、per-topic TTL、producer rate limiting）
- Producer interface（服务声明主题所有权）
- MCP 集成（AI agent 可编程操作终端）

**关键文件**：
- `packages/data/src/ditto_data/di/sources.py`
- `packages/engine/src/ditto_engine/alpha/protocols.py`
- `packages/data/src/ditto_data/provider.py`（DataProvider 归属问题）

#### 6. 维度五：Python 最佳实践

**审计项**：

| # | 审计项 | 方法 |
|---|--------|------|
| 6.1 | Protocol vs ABC 使用合规性 | 统计 88 Protocol 和 3 ABC，验证是否在正确场景使用 |
| 6.2 | 异常体系完整性 | 验证 5 域根是否覆盖所有源码异常，Engine 是否缺 errors.py |
| 6.3 | 类型安全一致性 | 检查 `dict[str, object]`、`str` 应为 `Literal`、frozen dataclass 一致性 |
| 6.4 | 现代 Python 特性利用度 | dataclass transform、TypeVar 泛型、match/case、 ParamSpec 等 |

**对标标准**：
- basedpyright strict mode（已实现）
- Protocol 优先于 ABC（已实现）
- Result union type for expected failures（未实现）
- entry_points 插件注册（未实现）

#### 7. 维度六：工程最佳实践

**审计项**：

| # | 审计项 | 方法 |
|---|--------|------|
| 7.1 | 测试架构平衡性 | 464 测试文件（414 unit + 45 integration + 5 e2e）的比例是否合理 |
| 7.2 | 配置管理闭环 | ConfigValidationProvider 未注册、DQSettings 未注入、os.environ 散落 |
| 7.3 | 观测一致性 | @traced 覆盖率、结构化日志 vs 字符串格式化 |
| 7.4 | CI/CD 门禁完整性 | arch-check + lint + type + test 覆盖的盲区 |
| 7.5 | 公共 API 管控 | 7 个包的 `__all__` 定义是否完整、re-export 链深度是否合规 |

#### 8. 维度七：Agent 编码最佳实践

**审计项**：

| # | 审计项 | 方法 |
|---|--------|------|
| 8.1 | 代码库可导航性 | 目录命名是否自解释、同名文件数量、README 覆盖 |
| 8.2 | 约定可执行性 | 哪些约定是机器执行的、哪些是文档-only |
| 8.3 | 大文件可理解性 | providers.py(533)、coordinator.py(739)、helpers.py(503) 等 |
| 8.4 | 决策树覆盖度 | Section 7 决策树是否覆盖所有边界情况 |
| 8.5 | 命名词典充分性 | 20 个后缀是否足够、是否有未覆盖的命名场景 |

**对标**：
- Marmelab 40+ Agent Coding Practices
- JetBrains Coding Guidelines for AI Agents
- Augment Code 12 Rules for AI-Ready Teams

#### 9. 维度八：可理解性综合评分

| 子维度 | 权重 | 评估方法 |
|--------|------|---------|
| 新人上手成本 | 20% | 按决策树走一遍"新增数据集"全流程 |
| Agent 正确编码率 | 20% | 评估 agent 在当前约定下做出错误放置的概率 |
| 命名传达信息量 | 15% | 看类名能否推断职责和归属层 |
| 依赖关系可推导性 | 15% | 从 import-linter 合约能否推导出完整依赖图 |
| 反模式识别效率 | 15% | CI 能否自动检测 Section 9 列出的 9 个反模式 |
| 文档与代码一致性 | 15% | boundaries 文档描述与实际代码的偏差 |

---

## Phase 2: 交付物二 — T0 差距分析与设计

产出文件：`docs/reviews/audit/2026-04-28-t0-gap-analysis-and-design.md`

### 2.1 T0 评分目标

| 维度 | 当前评分 | T0 目标 | 差距 |
|------|---------|---------|------|
| 架构能力 | A-(6.8→8.0) | A+(9.5) | Data 拆包、Port 归属统一、内部门禁 |
| 工程质量 | B+(7.5) | A(9.0) | 命名一致性、CQRS 纯净度、配置闭环 |
| 业务功能 | D+(3.5) | A-(8.5) | Order 概念、live/backtest 一致、风控、归因 |
| 可演进性 | B+(7.5) | A(9.0) | 插件化、DataPortal、状态机 |
| **综合** | **6.8** | **9.0** | |

### 2.2 关键差距设计（按优先级排序）

#### P1：Order 概念与生命周期（阻塞 live trading）

**差距**：TargetPortfolio → RebalancePlan 直接跳过 Order，无 submit/ack/partial-fill/cancel 状态机

**T0 参考**：
- NautilusTrader：Order 有 12 个状态（INITIALIZED → PENDING → ACCEPTED → PARTIALLY_FILLED → FILLED → CANCELLED → REJECTED → EXPIRED → TRIGGERED → INVALID → CANCEL_PENDING → MODIFY_PENDING）
- LEAN：Order 类含 OrderType (Market/Limit/StopMarket/StopLimit/MarketOnOpen/MarketOnClose) + OrderStatus + OrderEvents
- FinceptTerminal：CCXT 订单生命周期

**设计方案要点**：
- engine/accounting 新增 Order 聚合根（value object + 状态机）
- engine/execution 新增 OrderGateway Protocol（submit/cancel/modify）
- engine/backtest 新增 SimulatedBrokerage 实现 OrderGateway
- StrategyPipeline 输出从 TargetPortfolio 改为 Signal → Portfolio Construction → Order Generation → Execution
- 对齐 NautilusTrader 的 crash-only 状态机设计

#### P2：Backtest/Live 单代码路径

**差距**：当前仅有 batch backtest，无 TradingLoop 的 live 实现

**T0 参考**：
- NautilusTrader：单一 NautilusKernel 在不同 environment context 下运行（BacktestEngine/SandboxEngine/LiveEngine 共享策略/风控/组合逻辑）
- LEAN：同一 IAlgorithm 实例在 Backtesting/Benchmarking/LiveTrading 三种模式下运行
- FinceptTerminal：实时 WebSocket + 16 broker adapter

**设计方案要点**：
- engine/backtest/protocol.py 的 TradingLoop Protocol 已定义（架构基础就位）
- 新增 EnvironmentContext enum（BACKTEST/SANDBOX/LIVE）
- DataFeed Protocol 扩展：SimulatedDataFeed vs LiveDataFeed
- Brokerage Protocol 扩展：SimulatedBrokerage vs LiveBrokerage
- 策略代码零修改切换模式

#### P3：Data 包模块化重组

**差距**：340 文件 / 42,343 行占 43%，子域目标结构(Section 4.3)与实际结构有偏差

**T0 参考**：
- OpenBB：per-datatype Fetcher 粒度 + TET pipeline
- FinceptTerminal：DataHub pub/sub + topic-based addressing
- Django：app-based modular architecture

**设计方案要点**：
- 评估拆分方案：ditto-storage / ditto-sources / ditto-quality
- 或保持单包但强化内部子域门禁（类似当前 import-linter Data 子域隔离）
- 引入 DataCatalog 替代 Dataset StrEnum 的目录职责
- Storage Reader/Writer 薄包装合并

#### P4：Port 归属统一

**差距**：DataProvider 由实现方(data)定义，消费者(engine)被迫适应

**T0 参考**：
- Clean Architecture：port 由 application layer 定义
- Hexagonal Architecture：inbound port 属于 core，outbound adapter 实现 core 定义的接口

**设计方案要点**：
- 新增 engine/ports.py 定义 DataPortal Protocol（engine 需要的数据接口语义）
- Data 的 DataProvider 改为实现 engine/ports.DataPortal
- 逐步迁移其他跨平面 Port 到消费者侧

#### P5：DataPortal 扩展

**差距**：DataProvider 只有 4 个方法，远不够 full data access

**T0 参考**：
- Zipline DataPortal：get_history / get_spot_value / get_splits / get_dividends 等 15+ 方法
- NautilusTrader DataEngine：quote/trade/bar/orderbook 全类型支持
- LEAN DataManager：订阅制数据推送

**设计方案要点**：
- 定义 DataPortal Protocol（PIT-safe 查询、多 grain 支持、实时推送预留）
- 先在 engine/ports.py 定义接口，再由 data 逐步实现

#### P6：组件状态机与错误恢复

**差距**：backtest 循环用 try/except Exception 吞错误，无显式状态转换

**T0 参考**：
- NautilusTrader：组件 8 状态（PRE_INITIALIZED → READY → RUNNING → STOPPED → DISPOSED + DEGRADED + FAULTED）
- crash-only design：统一恢复路径、外部化状态、fail-fast on invariant

**设计方案要点**：
- 为 EngineLoop 引入显式状态机
- 替换 except Exception 为特定异常类型
- crash-only：NaN 价格、负时间戳、算术溢出立即终止

### 2.3 改进路线图

| 阶段 | 时间 | 目标 | 关键交付 |
|------|------|------|---------|
| **Sprint A（Quick Wins）** | 1 周 | 8.0 分 | ConfigValidationProvider 注册、DQSettings 注入、Analysis/AnalysisWarning 下沉、内部 import-linter 合约 |
| **Sprint B（命名收敛）** | 1 周 | 8.2 分 | PositionReader 重命名、_CatalogReader 合并、Dataset 业务逻辑提取、helpers 拆分 |
| **Sprint C（Order 概念）** | 2 周 | 8.5 分 | Order 聚合根 + 状态机 + SimulatedBrokerage |
| **Phase 2（Data 重组）** | 3 周 | 8.8 分 | Data 子域门禁强化、DataCatalog、薄包装合并 |
| **Phase 3（Live Parity）** | 4 周 | 9.1 分 | TradingLoop live 实现、EnvironmentContext、LiveDataFeed |
| **Phase 4（T0 平台化）** | 6 周 | 9.5 分 | DataPortal、生产运维、OMS、API 产品化、Web 工作台 |

---

## 执行步骤

### Step 1: 基线数据收集（只读）

- 运行 `pixi run -e dev check` 获取当前质量门禁状态
- 统计各维度指标（代码行数、Protocol 数、测试数等）
- grep 关键模式（命名冲突、CQRS 泄漏、os.environ 等）

### Step 2: 维度审计（只读分析）

按 8 个维度逐一审计，每个维度产出：
- 发现清单（P0/P1/P2 分级）
- 与业界最佳实践的差距
- 具体文件级别的改进建议

### Step 3: 对标补充

- 将 FinceptTerminal 加入 14 平台对标矩阵
- 重点借鉴：DataHub pub/sub、Producer interface、MCP 集成模式

### Step 4: T0 差距设计

对 P1-P6 差距分别产出：
- 当前状态描述
- T0 目标描述
- 具体设计方案（模块位置、Protocol 定义、依赖方向）
- 影响范围评估

### Step 5: 写入评估报告

写入 `docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`

### Step 6: 写入 T0 差距分析

写入 `docs/reviews/audit/2026-04-28-t0-gap-analysis-and-design.md`

### Step 7: 更新 boundaries 文档（如有需要）

根据审计发现，如需更新 `boundaries-and-abstraction-standards.md`，在执行阶段处理。

---

## 验证

- [ ] 评估报告覆盖 8 个维度，每个维度有具体发现和建议
- [ ] T0 差距分析覆盖 P1-P6，每个差距有完整设计方案
- [ ] FinceptTerminal 已纳入对标矩阵
- [ ] 所有发现都有文件级定位和严重度评级
- [ ] 改进路线图有明确的时间估算和优先级排序
- [ ] 运行 `pixi run -e dev check` 确认审计过程未引入变更
