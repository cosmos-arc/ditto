# Ditto 分层、模块化、命名与抽象层级规范

> 日期：2026-05-04
> 状态：Accepted
> 适用对象：后续 agent、个人开发者、架构审查者
> 关联材料：`CLAUDE.md`、各包 `CLAUDE.md`、`.importlinter`、`docs/reviews/audit/2026-04-24-current-full-project-audit.md`

## 1. 目的

本文件用于补足当前架构中“有边界但边界语言不够精确”的部分。它不是新的业务设计，也不是一次性重构计划，而是一份放置与命名规范。

任何开发者或 agent 在新增代码前，都应该能通过本文件回答以下问题：

1. 这个能力属于哪个架构平面？
2. 这个模块应该放在哪个包、哪个子目录？
3. 它应该叫 `Service`、`Provider`、`Adapter`、`Store`、`Registry` 还是别的名字？
4. 它应该依赖谁，谁可以依赖它？
5. 它处在哪个抽象层级，是否混入了更高或更低层的职责？

本文件的目标不是增加规则数量，而是给现有规则提供概念依据。`.importlinter` 能阻止明显越界，但不能判断“这个类的名字是否误导”“这个 port 应该由谁拥有”“这个 enum 是否承载了过多领域目录语义”。这些判断需要稳定的架构语言。

## 2. 总体判断

Ditto 当前的大分层已经成立，质量门禁也较强。主要不足不在于“没有分层”，而在于以下几类歧义：

| 歧义 | 典型表现 | 风险 |
|---|---|---|
| 架构平面与调用层级混在一起 | `data`、`features`、`analysis`、能力包容易被理解成简单上下层 | 后续代码可能把并列领域平面写成隐式上下游 |
| Apps 身份双重 | `apps` 同时像传输入口、composition root、provider 聚合层 | 业务逻辑、装配逻辑、流程编排容易混在一起 |
| 后缀词没有强定义 | `Service`、`Manager`、`Coordinator`、`Provider`、`Registry` 混用 | agent 会按附近名字仿写，长期导致概念漂移 |
| Port 归属不稳定 | 由实现方定义上游依赖接口 | 上游领域会被实现层语言污染 |
| Data 内部子域过大 | dataset、storage、quality、ingestion、runtime 语义散落 | 新数据集和新数据源扩展路径不唯一 |
| 包内部缺少子层合约 | Analytics expression 依赖 materialization contracts 等 | 包级门禁通过，但内部抽象方向反转 |
| Helper/Utils 逃逸 | 不确定逻辑容易进入 `helpers` / `utils` | 领域知识被埋进无语义目录 |

## 3. 架构心智模型

不要只把系统理解成一条线性的依赖链。更准确的模型是：

```text
                    apps
                     |
              application
                     |
   ┌──────────────── capability planes ────────────────┐
   | data  features  strategy  portfolio  risk          |
   | execution  backtest  analysis                      |
   └───────────────────────┬───────────────────────────┘
                           |
                         kernel

platform 是横向技术基础设施，只在包契约允许的范围内被导入。
analysis 当前实现 research dataset control-plane；product analysis namespaces
保持 reserved/future 状态，生产域包禁止依赖。
```

### 3.1 各平面定位

| 平面 | 定位 | 典型职责 | 不应承担 |
|---|---|---|---|
| `kernel` | 跨领域最小稳定语言 | 共享值对象、协议根、错误根、基础枚举 | 数据源、存储、回测、API、配置读取 |
| `platform` | 通用技术能力 | 配置基础设施、观测、并发、通知等 | 业务规则、数据目录、交易语义 |
| `data` | 数据平台平面 | 数据源、存储、目录、质量、摄取状态、数据查询 | 策略决策、回测执行、接口传输 |
| `features` | 因子计算平面 | 表达式、因子、物化计划、评估 | 策略决策、交易执行、外部 I/O |
| `strategy` | 策略定义平面 | 策略 pipeline、alpha 模板、信号生成 | 交易执行、回测运行、数据存储 |
| `portfolio` | 组合管理平面 | 持仓、会计、调仓、目标组合 | 交易执行、风控决策、数据源 |
| `risk` | 风险管理平面 | 盘前/盘后风控、约束、暴露度、回撤 | 策略决策、回测运行、数据存储 |
| `execution` | 交易执行平面 | 订单、成交、券商网关、费用、审计 | 回测运行、数据源适配、HTTP/CLI |
| `backtest` | 回测引擎平面 | 回测 runtime、step chain、绩效统计 | 数据源适配、HTTP/CLI、真实券商 |
| `analysis` | 研究分析平面 | research dataset control-plane；product analysis namespaces 保留给未来规划 | 被生产包导入、外部 I/O |
| `application` | 用例编排与组合平面 | commands/queries/processes、对象装配、跨平面用例 | 核心领域规则、物理 I/O 细节、传输协议 |
| `apps` | 传输适配平面 | FastAPI、CLI、Prefect job、请求响应模型、DI composition root | 业务计算、数据读写实现、引擎内部逻辑 |

### 3.2 垂直调用与水平平面

`data`、`features`、`strategy`、`portfolio`、`risk`、`execution`、`backtest` 是并列能力包。`application` 负责编排它们，`apps` 负责暴露它们。不要把某个能力包理解成天然高于另一个。

判断规则：

| 问题 | 放置倾向 |
|---|---|
| 它描述”数据是什么、从哪来、怎么存、质量如何” | `data` |
| 它描述”表达式、因子、统计评价、物化如何计算” | `features` |
| 它描述”策略定义、alpha pipeline、信号生成” | `strategy` |
| 它描述”持仓、会计、调仓、目标组合” | `portfolio` |
| 它描述”盘前/盘后风控、约束、暴露度” | `risk` |
| 它描述”订单、成交、券商网关、费用” | `execution` |
| 它描述”回测 runtime、step chain、绩效统计” | `backtest` |
| 它描述”研究数据集 control-plane（spec/snapshot/catalog/artifact）” | `analysis` |
| 它描述”一次用户用例如何串起各能力包” | `application` |
| 它描述”HTTP/CLI/job 如何接收请求并返回结果” | `apps` |

## 4. 包级职责标准

### 4.1 Kernel

`kernel` 只能放长期稳定、跨平面共享、无 I/O、无外部配置的概念。

允许：

- 共享错误根，例如 `DittoError`。
- 稳定值对象，例如 `InstrumentId`。
- 被多个核心平面共同消费的枚举和协议。
- 时间、市场、订单等最小共享语言。

禁止：

- 为单个包服务的便利类型。
- 数据集目录、外部数据源、存储 schema。
- 策略模板、回测配置、API DTO。
- 为了绕过 import-linter 而上提的临时类型。

判断句：如果一个类型只被一个平面需要，它不属于 `kernel`。

### 4.2 Platform

`platform` 是通用技术能力，不表达 Ditto 领域知识。

允许：

- 配置初始化基础设施。
- 观测、日志、指标、追踪。
- 文件锁、并发、通知等通用服务。

禁止：

- 数据质量规则。
- 数据源 token 的业务含义。
- 策略、订单、回测、数据集目录。

判断句：如果把 Ditto 换成另一个业务系统后该模块仍成立，它才可能属于 `platform`。

### 4.3 Data

`data` 是数据平台，不是“所有和数据有关的代码”的垃圾桶。

目标子域：

| 子域 | 目标职责 |
|---|---|
| `catalog` | 数据集标识、schema、分区、资产类别、日期语义、血缘元数据 |
| `sources` | 外部数据源 adapter、client、字段标准化 |
| `storage` | 物理读写、分区、SQLite/Parquet/DuckDB 细节 |
| `quality` | DQ 规则、执行、结果、隔离、报告 |
| `ingestion` | 摄取日志、游标、冻结、晚到数据、质量记录 |
| `query` | 面向上层的统一数据读取 facade |
| `runtime` | 运行期元数据和本地运行基础能力 |
| `di` | Data 内部对象注册 |

当前代码尚未完全拆成上述目标结构，但新增代码应尽量向这些语义靠拢。

Data 禁止：

- 依赖 `features`、`strategy`、`portfolio`、`risk`、`execution`、`backtest`、`analysis`、`application`、`apps`。
- 把策略决策或回测执行逻辑塞进 service。
- 在 `models` 中承载过多服务行为。
- 用裸字符串长期代表重要数据集概念。

### 4.4 Features

`features` 是因子、衍生数据和发布安全语义的能力平面。表达式、因子和物化计划等计算核心应该保持无外部 I/O；feature-owned 的持久化适配器位于 `storage/`，并由 DI 在应用边界组合。

目标内部层级：

```text
contracts/models
  -> expression
  -> factors
  -> materialization
  -> evaluation
  -> services/storage adapters
```

规则：

- `expression` 不应依赖 `materialization`。
- `factors` 应依赖表达式和因子 spec，而不是依赖 application process。
- `materialization` 负责计划和产物语义，不直接读写物理存储。
- `evaluation` 负责评价指标，不启动数据摄取或回测流程。
- 发布安全记录服务和发布安全运行时存储属于 `features`，不属于 `data.ingestion` 或 `data.storage.runtime`。

### 4.4b Analysis

`analysis` 是纯研究平面。

- `research` 负责研究数据集语义，不成为 Data catalog 的替代品。
- `reports`、`diagnostics`、`experiments`、`screeners` 当前只是 reserved/future namespaces，不是现有 runtime API。
- 生产域包禁止依赖 analysis；application 仅 research query/facade/DI wiring 可使用 analysis；apps 仅 research jobs/api/registry composition 入口可使用 analysis。
- 研究存储使用独立 SQLite。

### 4.5 Capability Packages（Strategy/Portfolio/Risk/Execution/Backtest）

原 Engine 已拆分为独立能力包。各包应该可以在没有 API、没有真实数据源、没有物理存储的情况下独立测试。

不要把能力包理解成一条 `strategy → portfolio → risk → execution` 的调用链。当前设计是并列能力包加显式编排：

```text
strategy   -> kernel, platform(storage/logging/tracing)
portfolio  -> kernel
risk       -> kernel, portfolio
execution  -> kernel, portfolio, platform
backtest   -> data, strategy, portfolio, risk, execution, kernel

application 编排能力包，apps 暴露 application。
```

硬性约束：

- `strategy` 不依赖 `portfolio`、`risk`、`execution`、`backtest`、`data`、`features`。
- `portfolio` 不依赖 `risk`、`execution`、`backtest`、`data`、`features`。
- `risk` 不依赖 `execution`、`backtest`、`data`、`features`、`strategy`。
- `execution` 不依赖 `risk`、`strategy`、`backtest`、`data`、`features`。
- `backtest` 不导入真实券商网关。
- 生产包不依赖 `analysis`。

各能力包规则：

- `strategy`：策略 pipeline、alpha 模板、信号生成。时间必须来自显式输入；存储适配可使用 platform 的 SQLitePool、logger、tracing。
- `portfolio`：持仓、会计、调仓。纯领域模型，不依赖 data 或 execution。
- `risk`：盘前/盘后风控、约束、暴露度、回撤。依赖 portfolio 的账户/订单视图，不依赖 execution。
- `execution`：订单、成交结果、真实券商端口、费用、审计。不依赖 risk 或 backtest。
- `backtest`：回测 runtime、step chain、绩效统计和模拟执行语义。`BacktestBrokerage`、fill/slippage/settlement 等模拟模型归 backtest；真实费用模型仍归 execution。

### 4.6 Application

`application`（原 app）是唯一业务用例编排层，也是对象装配的主要位置。它不应该包含底层领域规则，也不应该知道传输协议细节。

内部职责：

| 子目录 | 职责 | 禁止 |
|---|---|---|
| `queries` | 只读 facade，聚合读模型 | 写入、启动长流程、调用 command |
| `commands` | 写入命令 DTO 和 handler | 复杂长流程、查询 facade、对象构建 |
| `processes` | 长流程和跨服务编排 | 传输协议、物理存储细节、核心领域算法 |
| `builders` | 对象图构建和运行时装配 | 业务决策、外部 I/O、写入副作用 |
| `providers` | DI wiring | 业务流程、散落环境变量读取 |

判断规则：

- 如果是用户可触发的一次完整业务动作，优先看 `commands` 或 `processes`。
- 如果只是查询和组装读模型，放 `queries`。
- 如果只是创建对象图，放 `builders`。
- 如果只是注册对象，放 `providers`。

### 4.7 Apps

`apps` 是传输适配和 DI composition root，不是业务层。

允许：

- HTTP request/response DTO。
- CLI 参数解析。
- Prefect task/job 入口。
- 调用 application facade 或 application command。
- 把领域错误映射成 HTTP/CLI/job 响应。

禁止：

- 在 route 中计算业务指标。
- 在 route 中直接访问 storage/runtime。
- 在 job 中复制 Data catalog 的默认数据集清单。
- 用 `type(exc).__name__` 字符串匹配业务错误。
- 通过 `TYPE_CHECKING` 绕开边界。

组合根规则：

- `apps.registry/**` 是 DI composition root，允许直接导入具体能力包实现来完成 provider 装配。
- 普通 `api/`、`cli/`、`jobs/flows/`、`jobs/tasks/` 应调用 `application` facade、command 或 process，不直接导入能力包实现。
- `jobs/context.py` 只保留 Data Quality 引擎查找所需的窄豁免；新增豁免必须同步更新架构 smell guard 和测试。
- 非 registry 的能力包直连由 `check_apps_non_registry_capability_imports` 机器门禁守住。

## 5. 命名词典

后缀词必须表达架构角色，不允许只因为“附近有类似名字”而复用。

| 后缀 | 精确定义 | 可以做 | 不可以做 |
|---|---|---|---|
| `Provider` | DI 容器组件或窄能力提供者 | 注册对象、提供实现、适配 Protocol | 承载业务流程、读取散落 env、做复杂决策 |
| `ConfigInitProvider` | 配置初始化步骤 | 校验/创建启动前资源 | 承载业务配置解释 |
| `Service` | 稳定业务能力 | 围绕一个领域名词提供方法 | 编排完整长流程、处理 HTTP/CLI |
| `QueryFacade` | 只读用例门面 | 聚合查询、组装 read model | 写入、启动 flow、修改状态 |
| `CommandHandler` | 处理一个写入命令 | 校验命令、调用 service/process | 做多阶段长流程 |
| `Coordinator` | 一个完整流程的协调者 | 串联多个 service、处理流程状态 | 成为长期堆逻辑的大类 |
| `Orchestrator` | 跨平面/跨阶段编排器 | 管理明确 pipeline 或 workflow | 承载底层领域算法 |
| `Manager` | 有生命周期或状态资源的管理器 | 管理锁、缓存、运行期状态 | 作为模糊业务类名 |
| `Factory` | 创建对象 | 选择实现、组装构造参数 | 访问远端、写入存储、执行流程 |
| `Builder` | 构建复杂对象图或运行时对象 | 解析 spec、组装 engine/app 对象 | 读取接口请求、写业务结果 |
| `Registry` | 内存注册表或查找表 | 注册/查找类型、函数、适配器 | 初始化外部资源、执行业务流程 |
| `Catalog` | 有领域语义的目录 | 描述 dataset/spec/schema/lineage | 执行物理读写 |
| `Adapter` | 外部系统适配 | 把外部 API/文件转换为内部模型 | 暴露业务 use case |
| `Source` | 数据源聚合入口 | 组合 client/adapter/fetcher | 写入 storage、编排 ingest |
| `Store` | 物理持久化读写 | SQLite/Parquet 表和文件操作 | 数据源调用、业务流程 |
| `Reader` | 只读存储组件 | read/list/count/get | 写入、删除 |
| `Writer` | 写入存储组件 | write/upsert/delete | 查询编排、业务决策 |
| `Port` / `Protocol` | 消费者定义的依赖接口 | 描述消费者需要什么 | 复制实现方完整 API |
| `DTO` | 边界传输对象 | request/response/command/read model | 承载核心领域行为 |
| `Model` | 数据结构或领域模型 | 表达状态和值 | 访问 I/O 或容器 |
| `Rule` / `Checker` | 可组合规则 | 返回明确结果或问题列表 | 隐式修改全局状态 |

特别规则：

1. `Manager` 是受限词。新增 `Manager` 前必须能说明它管理的生命周期或状态资源是什么。
2. `Service` 不是万能后缀。若它只是查询门面，用 `QueryFacade`；若只是物理读写，用 `Store/Reader/Writer`；若只是外部适配，用 `Adapter`。
3. `Provider` 不等于业务服务。DI provider 中不应出现多分支业务流程。
4. `Registry` 和 `Catalog` 不同。Registry 偏技术注册，Catalog 偏领域目录。
5. 已知领域缩写在类名中保持大写：`ETF`、`FX`、`API`、`SQL`、`DQ`、`PIT`、`HTTP`。模块路径保持小写（`etf`、`fx`）。不要将公开类重命名为 `Etf` 或 `Fx`，这会丢失缩写信号。

## 6. 抽象层级一致性规则

### 6.1 一个模块只处在一个抽象层

同一个模块不应同时包含以下内容：

- HTTP request 解析和业务指标计算。
- 外部数据源调用和物理存储写入。
- DI 注册和领域规则。
- 表达式 AST 分析和物化执行编排。
- 回测 runtime 和订单领域模型变更。

如果一个文件需要同时知道“用户请求”“数据源”“存储路径”“业务规则”“响应模型”，它大概率在错误层级。

### 6.2 Port 由消费者拥有

默认原则：谁消费能力，谁定义 port。

例如：

- Strategy/Backtest 需要数据，应定义需要的数据 port 语义。
- Data 可以实现这个 port。
- Application 负责把 Data 实现注入消费方。

不要让实现方定义上游世界观。否则上游会逐步依赖实现层语言。

当前项目中 `ditto_data.provider.DataProvider` 被策略/回测包使用，是一个可运行折中。后续新增跨平面 port 时，应优先放在消费者包内，或放在 `kernel` 的最小共享契约中，并用 import-linter 固化。

### 6.3 领域目录优先于字符串枚举

重要业务概念不应长期以裸字符串流动。

| 情况 | 推荐 |
|---|---|
| 数据集标识 | `DatasetKey` / `DatasetSpec` / `DatasetCatalogEntry` |
| 数据源标识 | `SourceId` / `SourceSpec` |
| 运行环境 | `Environment` enum |
| DQ 等级 | `QualityLevel` / `DQTier` |
| 订单状态 | `OrderStatus` |

`StrEnum` 可以作为边界兼容层，但不应承担完整目录职责。如果 enum 开始拥有 asset class、date schedule、schema、存储路径、数据源映射，就应该迁向 catalog。

### 6.4 Helper/Utils 最小化

新增 `helpers` / `utils` 前必须先判断是否能放入更具体子域。

| 不推荐 | 推荐 |
|---|---|
| `utils/date.py` | `ingestion/date_range.py` |
| `helpers/path.py` | `storage/pathing.py` |
| `helpers/rules.py` | `quality/rule_selection.py` |
| `helpers/factor.py` | `features/factors/...` |

允许 helper 的条件：

- 纯函数。
- 无 I/O。
- 无跨层依赖。
- 没有业务状态。
- 文件名表达具体能力，而不是 `misc`、`common`、`utils`。

### 6.5 Public/Internal 边界

每个包都应该区分稳定公共入口和内部实现。

建议规则：

- 只有包 `__all__`、`public.py` 或包级 `CLAUDE.md` 明确列出的符号算稳定 API。
- `_internal`、`_runtime`、`_adapters`、下划线模块不允许跨包导入。
- 跨包导入应优先导入叶模块，不依赖深层 re-export 链。
- `__init__.py` 不应混合内联定义与大量 re-export。
- 包根不暴露运行时版本常量；版本展示使用 package metadata 或应用构建信息，不在各包 `__init__.py` 复制字符串。

## 7. 新代码放置决策树

新增代码前按顺序判断：

1. 它是否是跨平面稳定语言？
   - 是：考虑 `kernel`。
   - 否：继续。
2. 它是否是通用技术能力，和 Ditto 业务无关？
   - 是：考虑 `platform`。
   - 否：继续。
3. 它是否处理数据源、数据目录、存储、质量、摄取状态？
   - 是：考虑 `data`。
   - 否：继续。
4. 它是否处理表达式、因子、统计评价、物化？
   - 是：考虑 `features`。
   - 否：继续。
5. 它是否处理策略定义、alpha pipeline、信号生成？
   - 是：考虑 `strategy`。
   - 否：继续。
6. 它是否处理持仓、会计、调仓？
   - 是：考虑 `portfolio`。
   - 否：继续。
7. 它是否处理风控、约束、暴露度？
   - 是：考虑 `risk`。
   - 否：继续。
8. 它是否处理订单、成交、券商网关？
   - 是：考虑 `execution`。
   - 否：继续。
9. 它是否处理回测 runtime、step chain、绩效统计？
   - 是：考虑 `backtest`。
   - 否：继续。
10. 它是否处理研究数据集 control-plane（spec/snapshot/catalog/artifact）？
   - 是：考虑 `analysis`。
   - 否：继续。
11. 它是否把多个能力包串成一次用户用例？
   - 是：考虑 `application.processes` / `application.commands` / `application.queries`。
   - 否：继续。
12. 它是否只是 HTTP/CLI/job 的入口、参数、响应、错误映射？
   - 是：考虑 `apps`。
   - 否：暂停，补充架构讨论。

## 8. 扩展 Playbook

### 8.1 新增数据集

应修改：

1. Data catalog 或当前过渡期的 dataset 定义。
2. storage schema 和 reader/writer。
3. source fetcher/adapter。
4. ingestion 规则、日期语义、游标/日志。
5. quality 规则。
6. application queries/processes facade。
7. apps 只新增参数和响应，不复制数据集清单。

不应修改：

- Capability packages 核心模型，除非该数据集改变回测语义。
- Apps route 中的硬编码业务分支。
- Features 因子目录，除非该数据集直接提供因子输入。

### 8.2 新增数据源

应放：

- 外部 API/client/adapter：`data.sources.<source>`。
- 字段标准化：`data.sources.<source>` 或 `data.sources.schemas`。
- 数据源配置：`data.config`。
- DI 注册：`data.di.sources`。

不应放：

- `application.processes` 中直接调用外部 API。
- `apps` 中直接实例化 source。
- `storage` 中包含 source API 逻辑。

### 8.3 新增因子或表达式函数

应放：

- 表达式语言能力：`features.expression`。
- 因子 spec：`features.factors`。
- 物化计划：`features.materialization`。
- 数据保存：`data.storage` / `data.services`。
- 用例编排：`application.processes.materialization`。

不应放：

- Capability packages 中实现因子计算。
- Apps route 中拼接计算逻辑。
- Data storage 中写 factor 算法。

### 8.4 新增回测执行模型

应放：

- 真实费用模型和执行侧费用估算：`execution.reality`。
- 回测模拟成交、滑点、交收、模拟券商：`backtest.simulation` / `backtest.BacktestBrokerage`。
- 订单、成交、账户状态：`portfolio.accounting`。
- 回测 runtime 接入：`backtest`。
- 策略运行装配：`application.builders` / `application.processes.execution`。
- API 参数映射：`apps`。

不应放：

- Data service 中写执行模型。
- Apps route 中计算成交。
- Application provider 中写交易规则。

### 8.5 新增 API

应放：

- Request/Response：`apps`。
- 权限、参数解析、错误映射：`apps`。
- 只读业务：`application.queries`。
- 写入命令：`application.commands`。
- 长流程：`application.processes`。

route 只做薄适配。若 route 中出现超过少量分支的业务计算，应下沉到 `application`。

### 8.6 新增质量规则

应放：

- 规则定义和执行：`data.quality`。
- 质量记录持久化：`data.ingestion` / `data.storage.runtime.quality`。
- 巡检编排：`application.processes.quality`。
- job/API 触发：`apps`。

不应放：

- Apps job 中硬编码完整规则逻辑。
- Data source adapter 中直接决定 DQ 结果。

## 9. 常见反模式

| 反模式 | 为什么危险 | 正确方向 |
|---|---|---|
| Route 中做业务计算 | 传输层变业务层，测试和复用困难 | 下沉到 `application.queries` 或 `application.processes` |
| Provider 中写业务流程 | DI 层变隐式 use case | Provider 只 wiring，流程进 process/service |
| Manager 泛化 | 名字不能表达职责 | 改成具体领域名词，或证明其生命周期资源 |
| Dataset enum 继续膨胀 | enum 变数据目录和规则引擎 | 引入 catalog/spec |
| Port 由实现方定义 | 消费者被实现层语言污染 | port 放消费者侧 |
| Helper/Utils 承载业务 | 领域知识失去归属 | 移到具体子域 |
| TYPE_CHECKING 规避循环 | 架构问题被隐藏 | 调整依赖方向或提取契约 |
| 字符串匹配异常类型 | 错误语义脆弱 | 使用明确异常类和错误码 |
| 包级 re-export 链过深 | 真实依赖不可见 | 直接导入叶模块或明确 public API |

## 10. 机器门禁解释原则

当 `.importlinter` 的 layers 表达与架构模型看似冲突时，
以架构模型作为语义，以 explicit forbidden contracts 作为平面隔离依据。

## 11. 建议增加的架构门禁

当前 `.importlinter` 已覆盖包级和部分子域规则。下一阶段建议增加以下门禁：

| 门禁 | 目的 | 状态 |
|---|---|---|
| `features.expression` 禁止依赖 `features.materialization` | 固化 Features 内部抽象方向 | **已添加** ✅ |
| `strategy` 禁止依赖 `execution`、`backtest` | 防止下游依赖 | **已添加** ✅ |
| `execution` 禁止依赖 `backtest` | 防止 runtime 污染执行 | **已添加** ✅ |
| 生产包禁止依赖 `analysis` | 研究层隔离 | **已添加** ✅ |
| `apps.api.routes` 禁止依赖 `ditto_data.services` / `ditto_data.storage` | route 保持传输适配 | 待添加 |
| `application.providers` 禁止读取 `os.environ` | 配置入口集中 | 待添加 |
| `data.storage` 只允许依赖明确的 storage model/contracts | 收紧 storage-model 豁免 | 待添加 |
| `helpers/utils` 新增文件需要架构审查 | 防止无语义目录扩张 | 待添加 |

## 12. Agent 开发检查清单

开发前：

- 我能用一句话说明这个变更属于哪个架构平面。
- 我能指出它的消费者和提供者。
- 我知道它是否是 query、command、process、domain model、adapter、store 或 provider。
- 我检查过同类扩展的现有位置。
- 我没有因为 import 错误而使用 `TYPE_CHECKING` 绕过边界。

开发中：

- 新类后缀符合命名词典。
- 模块只处在一个抽象层。
- route/job/provider 中没有业务计算。
- 重要领域概念没有以裸字符串长期扩散。
- 新 port 由消费者拥有。

完成前：

- 运行 `pixi run -e dev arch-check`。
- 对涉及的包运行对应测试或全量快速验证。
- 若新增公共入口，更新包级 `CLAUDE.md` 或本目录文档。
- 若接受架构偏离，新增 ADR 或在审计报告中记录。

## 13. 当前最值得收敛的模糊点

按架构清晰度优先级排序：

1. 明确 `application` 的 composition root 边界，把 provider 从”可能做事”收紧为”只 wiring”。
2. 将 dataset 语义从 enum/string 迁向 catalog/spec。
3. 将消费者 port 放回消费者侧，减少实现方定义上游接口。
4. 给 Features 和各能力包增加包内部 import-linter 合约。
5. 把 `apps.registry` 的 composition root 豁免逐步迁到 `application.bootstrap` 或 `application.composition`。
6. 限制 `Manager`、`helpers`、`utils` 的新增。
7. 为每个包建立稳定 public API 清单。

## 14. 结论

Ditto 当前已经有较强的分层和门禁。下一阶段要解决的是“概念精度”问题：每个目录名、类后缀、port 位置和扩展入口都应该能说明它代表哪个领域概念、处在哪个抽象层、为什么只能放在这里。

架构清晰度的目标不是让系统看起来更复杂，而是让后续 agent 和个人开发者在没有额外解释的情况下，也能做出一致的放置、命名和依赖判断。

## 15. Agent 快速参考

> 机器可读的架构快速参考卡: [agent-context-pack.md](agent-context-pack.md)

## 16. T0 Architecture Clarity Acceptance Checklist

以下命令构成 T0 gate 的验收标准（所有项必须通过）：

```bash
# 代码架构门禁
python scripts/architecture/check_architecture_smells.py   # passes (0 issues)
pixi run -e dev lint-imports                                # 34 kept, 0 broken
pixi run -e dev type                                        # 0 errors, 0 warnings, 0 notes
pixi run -e dev test --fast                                 # all pass, 0 fail
pixi run -e dev arch-check                                  # passes
```

**功能性检查**：
- Tracing: `@traced` in `kernel.tracing` defaults to no-op; `install_trace_handler()` accepts handler; composition root wires OTel bridge
- DQ settings: `config_root` injected via DI, path resolution independent of process CWD
- Expression contracts: types owned by `expression.contracts`, `materialization` imports from canonical path
