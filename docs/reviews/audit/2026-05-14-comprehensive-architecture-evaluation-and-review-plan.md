# Ditto 架构综合评估与分模块 Review 计划

> 日期：2026-05-14
> 性质：对 `docs/reviews/audit/2026-05-13-comprehensive-architecture-evaluation.md` 的源码复核升级版
> 范围：12 包生产源码、架构守卫、运行时闭环、产品能力、业界最佳实践对标、全局及分模块攻坚计划
> 方法：源码抽样 + 指标扫描 + 关键路径阅读 + `pixi run -e dev arch-check` + 业界公开资料对标

---

## 0. 结论先行

Ditto 当前不是“架构不清”的项目，而是一个已经具备强边界治理、强类型约束、强测试文化的模块化量化平台雏形。真正的短板已经转移到三件事：

1. **运行时闭环不足**：Backtest 很成熟，但 Paper/Live runtime、BrokerGateway、对账恢复、订单状态同步仍没有形成可运行闭环。
2. **数据集扩展路径仍偏静态**：`Dataset` enum 仍承担运行时目录职责，application ingestion 仍有集中映射，新增数据集会触发多点修改。
3. **模块内部理解成本上升**：data/features/application 的若干 500-700 行文件、Service/Facade/Store 命名语义、占位 namespace、错误层级和类型不一致，开始影响长期演进。

因此，本报告不建议继续把目标表述为“修几个 review comment”。更准确的目标是：

> 用 6 个批次把 Ditto 从“优秀的研究/回测架构”推进到“可以承载 paper/live 演进的整洁模块化量化系统”。

---

## 1. 本次复核修正点

`2026-05-13` 报告方向基本正确，但本次按当前工作区源码复核后，有几处事实需要校准：

| 项目 | 2026-05-13 报告口径 | 2026-05-14 复核结果 | 影响 |
|---|---:|---:|---|
| 生产源码文件 | 897 | 897 | 一致 |
| 生产源码行数 | 103,419 | 103,425 | 轻微变动 |
| 测试文件 | 686 | 686 | 一致 |
| import-linter 合约 | 36 kept, 0 broken | 36 kept, 0 broken | 一致 |
| `type: ignore` in src | 0 | 0 | 一致 |
| `TYPE_CHECKING` in src | 0 | 0 | 一致 |
| pandas import in src | 0 | 0 | 一致 |
| Protocol 数量 | 161 | 121 个 Protocol class definition；289 个文本引用 | 需区分“类定义”和“文本引用” |
| ABC 数量 | 0 | 2 个 ABC class definition | 需要修正“ABC 归零”判断 |
| Dataset 使用 | application 282 处 / 23 文件 | application 126 行 / 11 文件；全 src 193 行 / 31 文件 | 旧报告偏高，但集中映射问题仍成立 |
| `noqa` in src/scripts | 66 | 70 | 轻微增加 |

两个仍存在的 ABC：

- `packages/platform/src/ditto_platform/foundation/config/initializer.py`：`ConfigInitProvider`
- `packages/platform/src/ditto_platform/services/notification/sender.py`：`NotificationSender`

这不构成架构错误，但说明当前并非 Protocol-only 风格。建议后续统一为 Protocol 或明确 ADR：哪些场景允许 ABC。

---

## 2. 当前源码快照

### 2.1 全局指标

| 指标 | 当前值 | 评估 |
|---|---:|---|
| 生产 Python 文件 | 897 | 大型模块化系统规模 |
| 生产源码行数 | 103,425 | 已进入需要强导航/边界纪律阶段 |
| 测试 Python 文件 | 686 | 测试资产充足 |
| import-linter 合约 | 36 | 边界机器可守，优秀 |
| arch-smells | passed | smell guard 已有效接入 |
| Protocol class definitions | 121 | 端口抽象成熟 |
| ABC class definitions | 2 | 风格存在局部不一致 |
| frozen dataclass | 364 | 不可变模型文化很强 |
| mutable dataclass | 10 | 多为运行态上下文/结果对象 |
| `type: ignore` in src/scripts | 0 | 优秀 |
| `TYPE_CHECKING` in src/scripts | 0 | 优秀 |
| pandas import in src/scripts | 0 | 符合项目铁律 |
| `noqa` in src/scripts | 70 | 可接受但需继续治理 |

### 2.2 逐包指标

| 包 | 文件 | 行数 | 测试文件 | Protocol class | 当前判断 |
|---|---:|---:|---:|---:|---|
| kernel | 14 | 914 | 16 | 5 | 小而稳，适合继续严控准入 |
| platform | 56 | 5,850 | 43 | 6 | 技术基础设施基本清楚，但 observability/config 复杂度偏高 |
| data | 286 | 31,491 | 192 | 20 | 最大包，扩展摩擦最大 |
| features | 108 | 15,136 | 34 | 23 | 表达式/因子能力强，大文件需拆 |
| strategy | 57 | 5,894 | 30 | 14 | 依赖隔离优秀，模板和 regime 子系统需整理 |
| portfolio | 21 | 1,486 | 16 | 10 | 核心会计简洁，但占位子域和市值语义需修 |
| risk | 18 | 1,381 | 23 | 5 | 返回值语义很好，runtime gate 尚缺 |
| execution | 49 | 3,629 | 34 | 13 | OMS Lite 成型，broker/reconciliation 未成闭环 |
| backtest | 39 | 5,192 | 42 | 6 | 当前最成熟模块 |
| analysis | 20 | 1,220 | 12 | 2 | 隔离好，但产品能力多为骨架 |
| application | 116 | 18,937 | 108 | 14 | CQRS/Process 清楚，但具体实现导入偏多 |
| apps | 113 | 12,295 | 136 | 3 | Composition Root 强，API/jobs 需要域内分包 |

### 2.3 Top 大文件信号

| 行数 | 文件 | 风险 |
|---:|---|---|
| 749 | `features/expression/codegen.py` | 编译器逻辑集中，理解成本高 |
| 697 | `features/evaluation/evaluator.py` | 评估策略聚合过多 |
| 697 | `data/services/metadata/instrument.py` | metadata service 过宽 |
| 672 | `data/storage/metadata/instrument/instrument_reader.py` | 查询构造和行转换可拆 |
| 629 | `data/storage/base/sqlite_store.py` | 泛化过强，SQL helper 可拆 |
| 629 | `data/sources/tushare/adapters/stock.py` | source adapter 承载过多 dataset |
| 622 | `features/evaluation/metrics/ic.py` | 指标计算职责过宽 |
| 592 | `application/processes/ingestion/data_writer.py` | Dataset 路由和写入职责集中 |
| 583 | `application/processes/materialization/orchestrator.py` | 物化编排复杂 |
| 583 | `application/processes/execution/backtest_process.py` | 回测 process 过大 |

行数不是罪，但这些文件已经成为 review 成本和修改风险的热点。后续拆分应按职责边界，而不是机械追求行数。

---

## 3. 总体评分

本次不使用单一分数，因为“工程架构质量”和“全球全市场 live-ready 产品成熟度”不是一回事。

| 口径 | 当前分 | 目标分 | 判断 |
|---|---:|---:|---|
| 工程架构综合质量 | **8.5 / 10** | 9.1 | 边界、测试、类型、不可变模型已优秀 |
| 整洁架构与依赖方向 | **8.3 / 10** | 9.0 | import-linter 很强；application 仍接触具体实现 |
| 可读性/一致性/命名治理 | **8.0 / 10** | 8.8 | 大文件、Service 后缀、errors/exceptions 混用拉低 |
| 数据平台扩展性 | **7.0 / 10** | 8.5 | PIT/storage 强，Dataset runtime 目录不足 |
| Backtest/Research 能力 | **8.6 / 10** | 9.2 | backtest 成熟，analysis 产品层仍薄 |
| Paper/Live runtime 就绪度 | **6.1 / 10** | 8.5 | PaperSynchronizer 和 BrokerGateway 未闭环 |
| 全球全市场产品架构完整度 | **5.4 / 10** | 8.0 | 多市场、多币种、broker、实时风控、产品体验仍缺 |
| 作为 T1 全栈量化平台 | **7.6 / 10** | 9.0 | 架构骨架强，产品闭环需要补课 |

一句话评分：

> Ditto 的代码边界治理是 8.5 分以上；作为真正 live-ready 的全球量化平台，目前仍是 5-6 分区间。下一阶段的重点不是继续证明包边界正确，而是把运行时、数据目录、交易闭环、产品能力补成体系。

---

## 4. 业界最佳实践对标

本节只取对 Ditto 当前阶段最有用的实践，不做“照抄竞品”。

### 4.1 LEAN / QuantConnect

官方文档说明 LEAN 是用于 research、backtesting、live trading 的开源算法交易引擎，并集成 common data providers 和 brokerages；LEAN 引擎负责 portfolio、data feeds、transactions、reality modeling 等基础能力，算法侧聚焦策略逻辑。

对 Ditto 的启发：

- **优点对齐**：Ditto 的 `strategy` 纯输入/输出、`backtest` step chain、`portfolio` accounting 和 `execution` OMS Lite 都在靠近这个方向。
- **主要差距**：LEAN 的 broker/data/portfolio/order 在同一运行时闭环内；Ditto 目前 `BrokerGateway` 仍是 Protocol-only，`PaperSynchronizer.stream()` 仍 `NotImplementedError`。
- **建议**：下一阶段优先做最小 Paper runtime，而不是继续只打磨回测报告。

### 4.2 NautilusTrader

NautilusTrader 明确强调 common core 被 backtest、sandbox、live 共享；同一策略实现可跨 research/live，系统使用 ports/adapters、event-driven、DDD，并有严格 domain model、UTC 时间模型和 backtest/live 语义一致性。

对 Ditto 的启发：

- **Ditto 强项**：12 包边界和 Protocol 隔离清楚；因子表达式/衍生数据能力比 Nautilus 的通用交易核心更偏研究。
- **Ditto 差距**：缺少真正共享的 runtime kernel。当前 `backtest` 成熟，但 Paper/Live 没有同一 loop、clock、broker、event journal、risk gate。
- **建议**：定义 `TradingRuntime` 或 `ExecutionRuntime`，让 backtest/paper/live 共享订单、风控、账户、事件和审计语义。

### 4.3 OpenBB Platform

OpenBB 的 extension/provider 体系强调 core + extension，数据和工具能力可以按 provider/extension 安装、发现和路由。

对 Ditto 的启发：

- **Ditto 强项**：data storage、quality、PIT、source adapter 都有基础。
- **Ditto 差距**：`Dataset` enum 仍是静态目录；新增 dataset 要改 enum、fetch handler、writer、quality、config 等多处。
- **建议**：短期做 `DatasetRegistry` 集中路由；中期把 `DataCatalog` runtime 化，承载 dataset metadata、fetch/write capability、asset class、schedule、quality profile。

### 4.4 vn.py / VeighNa

vn.py 生态长期强调事件驱动引擎和 gateway 接入，覆盖大量国内外市场交易接口。它的优势不是整洁架构，而是交易端产品闭环和 gateway 生态。

对 Ditto 的启发：

- **Ditto 强项**：包边界、测试、PIT/backtest 更现代。
- **Ditto 差距**：交易 gateway、事件驱动状态同步、实盘运维和连接恢复还没形成。
- **建议**：至少实现 paper/mock gateway，再定义 QMT/XTP/IBKR 等真实 gateway 的 adapter contract 和 conformance tests。

### 4.5 FinRL / FinRL-X

FinRL 传统文档强调 market environment、agent、application 三层结构；2026 年 FinRL-X 论文进一步强调 data processing、strategy construction、backtesting、broker execution 在统一协议下保持 deployment consistency，并用 weight-centric interface 连接规则策略、AI 组件和下游执行。

对 Ditto 的启发：

- **Ditto 强项**：`strategy` 已经输出 `TargetPortfolio`，天然适合 weight-centric pipeline；`features` 表达式引擎也适合承载规则/AI 因子。
- **Ditto 差距**：策略输出到执行再到 paper/live 的一致协议还不完整；AI/RL 不是当前核心，但未来应作为 strategy/allocator plugin，而非改动 execution。
- **建议**：保持“策略只给目标/信号，执行处理约束和交易细节”的方向，避免 AI 组件直接侵入 broker/execution。

### 4.6 Zipline-reloaded / VectorBT

Zipline-reloaded 代表 Pythonic event-driven backtesting 和 PyData 研究工作流；VectorBT 代表大规模向量化参数扫描、交互式研究和批量策略评估。

对 Ditto 的启发：

- **Ditto 强项**：项目禁止 pandas，使用 Polars，且已有因子表达式、PIT 和 backtest step chain，工程约束更强。
- **Ditto 差距**：批量参数扫描、研究体验、交互式分析、结果探索还比较弱。
- **建议**：不要引入 pandas 生态依赖；应在 `analysis` + `features` + `backtest` 上构建 Polars-first 的 parameter sweep 和 result cube。

### 4.7 业界对标结论

| 能力 | Ditto 当前 | 业界优秀实践 | 差距判断 |
|---|---|---|---|
| 包边界治理 | 很强 | 多数开源框架未机器化约束 | Ditto 领先 |
| PIT/数据防泄漏 | 强 | 研究平台通常靠约定 | Ditto 较强 |
| 因子表达式 | 强 | LEAN/Nautilus 不以内置因子 DSL 为主 | Ditto 特色 |
| Backtest 引擎 | 强 | LEAN/Nautilus 成熟 | 接近但还需 runtime parity |
| Backtest/Paper/Live 一致性 | 弱 | Nautilus/LEAN 核心优势 | 明显落后 |
| Broker gateway | 弱 | LEAN/vn.py/Nautilus 成熟 | 明显落后 |
| 数据 provider 插件化 | 中 | OpenBB/LEAN 更成熟 | 需要 DataCatalog runtime |
| 多市场产品能力 | 初期 | LEAN/vn.py 覆盖广 | 明显落后 |
| 研究体验/批量扫描 | 中弱 | VectorBT/OpenBB/Jupyter 生态强 | 需要 analysis 产品化 |

---

## 5. 全局架构判断

### 5.1 当前优势

1. **边界守卫优秀**
   `.importlinter` 里 36 条合约全部 kept，覆盖 package 层、application R8、data storage 子域、source isolation、analysis 双向隔离、acyclic siblings。

2. **生产源码纪律强**
   `type: ignore`、`TYPE_CHECKING`、pandas import 在生产源码和 scripts 中均为 0。对 Python 大型项目来说，这是非常强的信号。

3. **不可变数据模型文化成熟**
   364 个 frozen dataclass，订单、账户快照、风险动作、策略配置等核心跨边界对象多数不可变。

4. **Backtest 已经接近标杆模块**
   Step Chain、PIT、防前瞻、审计、manifest、replay、simulation models 都具备产品级雏形。

5. **Strategy 包隔离非常好**
   不依赖 data/features/portfolio/risk/execution/backtest，通过输入包和 Protocol 反转依赖，这一点非常值得保留。

### 5.2 当前高风险短板

1. **Dataset 仍是运行时目录**
   `packages/data/src/ditto_data/models/common.py` 的 `Dataset` 不只是类型枚举，还包含 asset class、date schedule、basic/calendar 判断等运行时知识。application ingestion 又维护 Dataset 到 fetch/write 的映射，导致扩展摩擦高。

2. **Application 中有过多具体实现 wiring**
   `queries/source.py` 直接返回 `TushareSource | FredSource`；`providers_process.py` 直接使用 `SQLiteClient`、features runtime stores、data services；`providers_command.py` 直接装配 data storage/quality/source。DI provider 可以接触实现，但当前 application 和 composition root 的边界仍混杂。

3. **Paper/Live runtime 仍未起跑**
   `PaperSynchronizer.stream()` 未实现，`execution.broker.gateways` 为占位，`ReconciliationReport` 只是 dataclass。执行闭环不足会限制所有 live-ready 评分。

4. **风险、执行、组合三者还没有 runtime spine**
   `risk` 很干净，但缺 `RiskGate`；`execution` 有 OMS Lite，但没有 broker adapter；`portfolio` 有 accounting，但与 execution/reconciliation 的状态恢复链还不完整。

5. **数据/特征/application 大文件成为维护热点**
   700 行文件虽未触发 smell guard，但已经显著增加 review 成本。下一步应按职责拆分，而不是继续堆 helper。

---

## 6. 逐模块评估与建议

### 6.1 kernel — 8.6 / 10，目标 9.0

**定位**：全系统共享语言，必须极小、稳定、零 I/O。

**优势**

- 14 文件、914 行，边界清晰。
- `Clock`、`EventBus`、`Synchronizer` 等核心抽象合理。
- `InstrumentId`、订单方向、市场快照、trading rule 等跨包语言集中。

**问题**

- `trading.py` 同时承载 `FeeModel`、`InstrumentRules`、`MarketSnapshot`，未来多市场扩展时可能膨胀。
- `MarketSnapshot` 已含 A 股初期字段，全球化后需要 session/venue/microstructure 扩展策略。
- `EventName` 与 `DomainEvent.event_type: str` 的类型边界不完全一致。
- `tracing.py` 使用全局 trace handler，未来并发/多 runtime 场景需更谨慎。

**Review 计划**

- 检查 kernel 准入标准：是否真的被 3 个以上包共享，是否无 I/O，是否无市场特化行为。
- 为 `trading.py` 类型归属做 ADR：保留 kernel 还是迁回 execution/backtest/data。
- 明确 A 股初期字段标注和全球市场扩展方案。

### 6.2 platform — 7.7 / 10，目标 8.5

**定位**：横切技术基础设施，允许依赖 kernel，但不能泄漏业务语义。

**优势**

- storage/cache/config/observability/db/util 子域清晰。
- XDG path、SQLite pool、observability、notification 都具备可用基础。
- import-linter 已防止 platform 依赖业务包。

**问题**

- `observability/metrics.py` 534 行，动态 registry/metaclass/provider 逻辑集中。
- `ConfigInitProvider`、`NotificationSender` 仍使用 ABC，与全库 Protocol 风格不一致。
- `paths.py` 520 行，历史兼容函数和属性模式可拆。
- notification settings 出现微信/钉钉字段，属于传输 adapter 具体字段，但需要确认是否仍算平台基础设施。

**Review 计划**

- 拆 metrics registry、metric definition、provider binding。
- 统一 ABC 策略：迁 Protocol，或写 ADR 说明 ABC 允许场景。
- 清理 config path 死代码和重复属性生成。
- 检查 platform 是否出现领域名词：instrument、strategy、portfolio、risk 等应保持 0。

### 6.3 data — 7.0 / 10，目标 8.5

**定位**：数据平台，负责获取、存储、查询、PIT、防泄漏和质量。

**优势**

- storage 按 market/fundamental/capital/metadata/runtime/macro 分域。
- data sources 与 storage 隔离，source 子域互斥合约已守住。
- PIT helper、quality、runtime freeze、ingestion log/cursor 基础扎实。
- root barrel 克制。

**问题**

- 最大包：286 文件、31,491 行，占全仓 30% 左右。
- `Dataset` enum 承担过多运行时目录职责。
- `catalog/contracts.py`、`lineage/contracts.py` 仍偏 contract-only，runtime 价值未释放。
- `providers/`、部分 reserved namespace 和 source 空壳增加导航噪音。
- metadata service/reader、sqlite store、Tushare adapter 大文件多。

**Review 计划**

- P0：设计 `DatasetRegistry`，集中 fetch/write/schedule/quality profile 路由。
- P1：推进 `DataCatalog` runtime，实现 dataset metadata 查询、capability discovery、schema/version/profile。
- P1：拆 `metadata/instrument.py`、`instrument_reader.py`、`sqlite_store.py`。
- P2：清理空壳目录和文档漂移。
- P2：给 data 内部再加子域级 smell/check：新增 dataset 必须注册到 registry，而不是散落 if/elif。

### 6.4 features — 8.5 / 10，目标 9.0

**定位**：因子表达式、衍生数据、物化、评估。

**优势**

- expression pipeline 清楚：lexer/parser/ast/analyzer/compiler/codegen。
- 因子 registry 模式统一，适合扩展。
- materialization 与 expression 边界有合约。
- publication safety、shadow publish、derived catalog 已有产品化意识。

**问题**

- `expression/codegen.py` 749 行，全库最大。
- `evaluation/evaluator.py` 697 行，策略和报告逻辑集中。
- `evaluation/metrics/ic.py` 622 行，指标维度过宽。
- `FeaturesError` 与 `DerivedError` 错误根并列，捕获语义不够顺。
- services 目录混合 derived catalog、publication safety、artifact/query/gc。

**Review 计划**

- 拆 codegen：表达式节点 visitor、polars expr generation、diagnostics 分离。
- 拆 evaluator：输入准备、分组、metrics dispatch、report build 分离。
- 统一错误层级：`DerivedError` 继承 `FeaturesError`。
- services 按 `derived/`、`publication/`、`evaluation/` 分域。

### 6.5 strategy — 8.6 / 10，目标 9.0

**定位**：策略定义与信号生成，不依赖 data/features/portfolio/risk/execution/backtest。

**优势**

- 依赖隔离是全仓范例。
- Pipeline 和 InputBundle 方向正确。
- stage/factory/config/validate 模式一致。
- Strategy 只表达意图，不绑定执行，符合 FinRL-X 的 weight/target-centric 思路。

**问题**

- `builtins/regime_*.py` 扁平，regime 子系统已经值得独立子包。
- root `__init__.py` 空导出，用户体验弱。
- 模板层仍有大文件和跨 stage/config 聚合。

**Review 计划**

- 提取 `alpha/builtins/regime/` 子包。
- 为 root 提供 3-5 个稳定顶层符号，避免过度 re-export。
- 拆 stock sector rotation 模板，配置、stages、factory 分离。

### 6.6 portfolio — 7.7 / 10，目标 8.5

**定位**：组合构建、账户、头寸、现金、调仓。

**优势**

- `Account` 是唯一主要可变状态持有者，`AccountView` frozen snapshot 方向正确。
- Fill、Position、CashBook 等核心值对象简洁。
- `report_views.py` 用 Protocol 解耦 backtest 报告结构，是好方向。

**问题**

- `Account` 使用 `@dataclass` 但自定义 `__init__`，装饰器贡献有限。
- sell path `market_value` 使用 average cost 的语义需复核。
- `holdings/`、`positions/` 多为 Protocol 存根，产品能力薄。
- `target_portfolios/` 仍是 reserved。

**Review 计划**

- 修正 sell path 市值语义并补测试。
- Account 改普通类或真正 dataclass。
- positions/holdings 统一 `InstrumentId` 类型，并明确是否继续保留子域。
- 增加组合层目标组合/调仓报告的产品化接口。

### 6.7 risk — 7.4 / 10，目标 8.5

**定位**：风控规则、约束、暴露、post/pre trade guard。

**优势**

- 返回值语义清楚：风控拒绝/调整不是异常。
- PreTradeContext frozen，resize/recheck 循环清楚。
- post-trade action 模型简洁。

**问题**

- `SliceView.bars: dict[InstrumentId, Any]` 是核心类型安全缺口。
- `_accept()` helper 重复。
- 缺 runtime `RiskGate`，无法挂入 submit/modify/fill/live recovery。
- RiskAction、backtest audit、execution audit 尚未共享 trace/correlation ID。
- `models.py` reserved 空壳。

**Review 计划**

- 定义窄 `BarSlice` Protocol，替代 `Any`。
- 提取 pre-trade accept helper。
- 删除或填充 reserved `models.py`。
- 设计 `RiskGate` Protocol：pre-submit、pre-cancel、post-fill、daily-scan。

### 6.8 execution — 7.2 / 10，目标 8.6

**定位**：订单、OMS、执行计划、broker adapter、审计、对账。

**优势**

- OMS Lite 方向正确：ClientOrderId/BrokerOrderId、OrderTicket frozen update、OrderBook、journal、FSM。
- `ClientOrderId.generate()` 已提供全局唯一策略。
- 订单状态机和 overfill guard 有基础。
- Planner 已从单体拆分到多个 helper。

**问题**

- `BrokerGateway` 仍为 Protocol-only，`broker/gateways` 是占位。
- `ReconciliationReport` 只是 dataclass，无 matching、store、repair flow。
- `PaperSynchronizer` 在 application runtime 中未实现，execution 无 paper gateway 闭环。
- `OrderBook.cancel()` 与 submit/update 的 journal-first 策略需统一审视。
- root `__init__.py` 空导出，稳定 API surface 弱。

**Review 计划**

- P0：实现 `PaperBrokerGateway`，接 OMS、AccountView、FillStore。
- P0：最小 reconciliation：expected orders/fills vs actual broker fills，产出 diff。
- P1：统一 OrderBook event mutation 模式。
- P1：所有生成订单使用 `ClientOrderId.generate()`。
- P2：定义 broker adapter conformance tests。

### 6.9 backtest — 8.8 / 10，目标 9.2

**定位**：回测引擎、仿真、绩效、审计、replay。

**优势**

- Step Chain 架构清楚，DataFetch/RiskScan/Strategy/Planning/PreTrade/Execution/Audit 职责明确。
- PIT、防前瞻、manifest、replay、simulation models 都较完整。
- 与 execution/portfolio/risk 的集成已经具备系统味道。

**问题**

- `StepContext` 是共享可变状态，没有 phase/state guard，step 乱序可能以 None 形式延迟失败。
- `EngineResult` mutable dataclass，与跨边界不可变惯例不一致。
- statistics returns 里仍有手动数值计算和重复 NAV->return 逻辑。
- cancellation/timeout 只在较粗粒度上存在。

**Review 计划**

- 为 StepContext 加 required getter 或 phase guard。
- EngineResult 改 frozen final result；运行中累积状态另建 builder。
- 清理 returns 计算重复。
- 为 long-running backtest 增加 step-level cancellation hook。

### 6.10 analysis — 7.8 / 10，目标 8.6

**定位**：研究分析层，不能反向污染生产包。

**优势**

- 与生产包双向隔离清楚。
- research catalog/storage 有雏形。
- late arrival 策略有设计意识。

**问题**

- diagnostics/screeners/reports/experiments 都是 reserved namespace。
- ResearchCatalogService 多为 pass-through。
- ArtifactService 依赖 filesystem glob/path 解析，缺 manifest/index。
- Record 从 SQLite 读取后验证不足。

**Review 计划**

- 保留 research catalog，去掉或明确 reserved namespace 的产品路线。
- Record 添加 `from_row()` 验证工厂。
- ArtifactService 改 manifest/index 驱动。
- 构建 Polars-first research result cube / sweep 计划。

### 6.11 application — 7.7 / 10，目标 8.8

**定位**：CQRS 编排层，不应成为第二个 composition root。

**优势**

- queries/commands/processes/builders R8 互斥规则清楚。
- Process Manager 的长流程编排方向正确。
- Facade 模式对 apps 隐藏内部复杂度。

**问题**

- `queries/source.py` 直接导入并暴露 `TushareSource | FredSource`。
- `providers_process.py`、`providers_command.py` 直接装配大量 data/features/platform 具体实现。
- `fetch_handlers.py` 维护 Dataset -> lambda 映射。
- 多个 500 行级 process/facade 文件。

**Review 计划**

- P0：SourceQueryFacade 改为应用层 Protocol 返回 primitives，不暴露 concrete source。
- P0：DatasetRegistry 从 application ingestion 中抽出。
- P1：providers 中物理存储、SQLite、source adapter wiring 下沉 apps/registry。
- P2：拆 backtest_process、data_writer、materialization orchestrator。

### 6.12 apps — 8.2 / 10，目标 8.8

**定位**：入口、API、CLI、jobs、composition root。

**优势**

- registry/container 是全仓 composition root，方向正确。
- API/CLI/jobs 分层基本清楚。
- apps 测试文件多，架构测试集中。

**问题**

- routes 数量增长，域内分包需求出现。
- jobs/context 仍有 data.quality 窄豁免。
- startup/init provider 与 DI provider 职责边界可再清。
- 部分 API endpoint 是 V1 占位。

**Review 计划**

- routes 按 `trade/market/data/strategy/backtest/admin` 分包。
- startup 初始化从 provider 文件分离。
- DQ context 豁免给出迁移路线：kernel 候选类型或 application bundle。
- 清理占位 endpoint 的成熟度标注。

---

## 7. 全局攻坚路线

### 7.1 优先级定义

| 优先级 | 含义 | 验收 |
|---|---|---|
| P0 | 阻塞扩展或运行时闭环 | 完成后能减少多点修改或跑通新路径 |
| P1 | 高收益整洁架构修复 | 降低模块耦合、类型缺口或状态风险 |
| P2 | 可读性/一致性治理 | 大文件、命名、错误层级、文档漂移 |
| P3 | 体验和长期演进 | barrel、reserved namespace、低风险 polish |

### 7.2 六个攻坚批次

#### Batch 1：DataCatalog / DatasetRegistry（P0）

目标：遏制 Dataset enum 承担 runtime 目录职责。

任务：

- 新增 `DatasetRegistry`：dataset -> fetch capability、writer capability、asset class、date schedule、quality profile。
- 改造 `fetch_handlers.py`、`data_writer.py`、`coordinator_constants.py` 使用 registry。
- 为新增 dataset 写一个 conformance test：只注册一处即可参与 fetch/write。
- 保留 `Dataset` enum 作为稳定 ID，不再让它承担全部行为。

验收：

- 新增一个 mock dataset 不需要修改 3 个以上 application 文件。
- `pixi run -e dev arch-check` 通过。
- ingestion 相关单元测试覆盖 registry 路由。

#### Batch 2：Paper Runtime + BrokerGateway（P0）

目标：跑通最小 paper trading 闭环。

任务：

- 实现 `PaperSynchronizer.stream()` 最小版本。
- 实现 `PaperBrokerGateway`，接 `BrokerGateway` Protocol。
- BrokerGateway submit/cancel/query_fills 与 OMS OrderBook/Journal 同步。
- 最小 reconciliation：expected order/fill 与 broker reported fill 对比。

验收：

- 一个策略目标组合可以从 signal -> plan -> order -> paper fill -> account view。
- cancellation 和 partial fill 有测试。
- reconciliation report 不再只是 pending dataclass。

#### Batch 3：Application Composition Boundary（P1）

目标：application 不再成为第二个 composition root。

任务：

- `SourceQueryFacade` 不返回 `TushareSource | FredSource`。
- SQLite/source/physical store wiring 下沉 apps/registry。
- application providers 只装配 application use case 和 Protocol。

验收：

- application 中具体 source adapter import 数下降。
- application 中 `SQLiteClient` import 消失或仅留明确例外。
- import-linter 增补 application-concrete-storage-smell。

#### Batch 4：Execution/Risk/Portfolio Runtime Spine（P1）

目标：交易、风控、组合形成一致运行时语义。

任务：

- 定义 `RiskGate`：pre-submit、pre-cancel、post-fill、daily-scan。
- `SliceView.bars` 替换 `Any`。
- Account/Order/Fill/Reconciliation 共享 correlation/run/trade date 语义。
- portfolio sell market value 语义修正。

验收：

- 风控可以嵌入 paper submit 路径。
- fill 进入 portfolio 后可被 reconciliation 和 audit 追踪。
- 关键对象类型均使用 `InstrumentId`。

#### Batch 5：大文件和命名一致性治理（P2）

目标：降低 review 成本，提高可读性。

任务：

- 拆 `features/expression/codegen.py`。
- 拆 `features/evaluation/evaluator.py` 和 `metrics/ic.py`。
- 拆 data metadata/instrument 和 sqlite_store。
- 统一 Service/Facade/Store/Reader/Writer/Coordinator/Process 命名规则。
- 统一 `errors.py` / `exceptions.py` 策略。

验收：

- 每个拆分 PR 有等价测试，行为不变。
- 大文件减少，职责边界可一句话说明。
- 命名规则写入 architecture standard。

#### Batch 6：Product Architecture Gap Closing（P2/P3）

目标：从工程系统走向产品平台。

任务：

- analysis 做 Polars-first research sweep / result cube 设计。
- apps API maturity 标注：experimental/beta/stable。
- 多市场路线：calendar/session、currency、venue、asset-class profile。
- observability dashboard：runtime、ingestion、broker、risk、backtest 指标统一。

验收：

- 有产品路线文档和 API maturity matrix。
- 指标/日志/trace 覆盖 ingestion/backtest/paper runtime 主路径。

---

## 8. 分模块 Review 检查清单

每个模块攻坚时，统一采用以下 review 模板。

### 8.1 通用检查

- 边界：是否新增违反 `.importlinter` 精神的具体依赖？
- 抽象：Protocol 是否由消费者拥有？是否过宽？
- 类型：是否引入 `Any`、`type: ignore`、`TYPE_CHECKING`？
- 数据：是否 frozen？若可变，生命周期是否明确？
- 命名：Service/Facade/Store/Reader/Writer 是否符合职责？
- 错误：业务返回值和异常语义是否分离？
- 测试：是否有 RED/GREEN 证据？是否覆盖错误路径？
- 文档：CLAUDE/AGENTS/ADR 是否随架构变化更新？

### 8.2 模块顺序

| 顺序 | 模块 | 原因 |
|---:|---|---|
| 1 | data + application ingestion | Dataset 扩展摩擦最大，影响后续所有数据能力 |
| 2 | execution + application runtime | Paper/Live 闭环是产品架构最大短板 |
| 3 | risk + portfolio | 交易闭环必须接风控和会计 |
| 4 | application providers + apps registry | 收紧 composition root |
| 5 | features + strategy | 提升可读性和策略扩展体验 |
| 6 | backtest + analysis | 保持强项，补研究产品化 |
| 7 | kernel + platform | 最后清理基础层，避免过早搬动共享语言 |

---

## 9. 评分提升路线

| 阶段 | 完成内容 | 工程架构 | Runtime | 产品完整度 |
|---|---|---:|---:|---:|
| 当前 | 边界强，backtest 强，paper/live 弱 | 8.5 | 6.1 | 5.4 |
| Batch 1 后 | DatasetRegistry 降低扩展摩擦 | 8.7 | 6.2 | 5.8 |
| Batch 2 后 | Paper runtime 最小闭环 | 8.7 | 7.2 | 6.4 |
| Batch 3-4 后 | application 下沉 wiring，risk/execution/portfolio spine | 8.9 | 7.8 | 7.0 |
| Batch 5 后 | 大文件/命名/错误层级治理 | 9.1 | 7.9 | 7.1 |
| Batch 6 后 | 产品路线和研究体验补齐 | 9.1 | 8.0 | 7.8 |

真正达到全球全市场 live-ready 的 8.5+，还需要真实 broker adapter、多币种会计、多市场 session/calendar、实时数据质量、权限/审计/运营后台，这不应塞进当前 6 个攻坚批次。

---

## 10. 验证命令

本次已运行：

```bash
pixi run -e dev arch-check
```

结果：

```text
Contracts: 36 kept, 0 broken.
Architecture smell check passed.
```

后续每个批次完成前必须运行：

```bash
pixi run -e dev check
```

如果只做设计/文档批次，至少运行：

```bash
pixi run -e dev arch-check
```

---

## 11. 外部参考资料

- QuantConnect LEAN Algorithm Engine: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine
- QuantConnect live trading orders: https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/trading-and-orders
- NautilusTrader architecture: https://nautilustrader.io/docs/latest/concepts/architecture/
- NautilusTrader overview: https://nautilustrader.io/docs/latest/concepts/overview/
- OpenBB extension overview: https://docs.openbb.co/platform/usage/extensions/overview
- OpenBB architecture overview: https://docs.openbb.co/platform/developer_guide/architecture_overview
- FinRL three-layer architecture: https://finrl.readthedocs.io/en/latest/start/three_layer.html
- FinRL-X paper: https://arxiv.org/abs/2603.21330
- Zipline-reloaded repository/documentation: https://github.com/stefan-jansen/zipline-reloaded
- VectorBT documentation: https://vectorbt.dev/
- vn.py official site: https://www.vnpy.org/

---

## 12. 自审结果

- 未完成项扫描：未发现空白章节、未决标记或未决范围；“占位”仅用于描述当前源码现状。
- Internal consistency：评分区分工程架构、runtime、产品完整度，避免口径冲突。
- Scope check：报告覆盖全局评估和分模块 review 计划，但不直接进入代码实现。
- Ambiguity check：P0/P1/P2/P3 均给出验收标准，后续可逐批次拆实施计划。

---

## 13. 最终建议

下一步不要平均用力。建议第一轮只打 **Batch 1：DataCatalog / DatasetRegistry**。

原因：

- 它是当前扩展性最大痛点。
- 它牵动 data/application，但不需要立即碰 broker/live 高风险路径。
- 做完后会立刻降低新增数据集的认知负担。
- 它能为后续 OpenBB 式 provider/catalog 架构打地基。

第一轮完成后，再进入 **Batch 2：Paper Runtime + BrokerGateway**，把 Ditto 从强回测系统推进到真正可验证的运行时系统。
