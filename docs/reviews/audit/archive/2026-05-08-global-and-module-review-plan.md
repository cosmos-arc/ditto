# Ditto 全局与分模块架构 Review 计划报告

> 日期：2026-05-08
> 输入报告：`docs/reviews/audit/2026-05-07-comprehensive-architecture-evaluation.md`
> 关联证据：`docs/reviews/audit/2026-05-07-deep-architecture-evaluation.md`、`docs/reviews/audit/2026-05-08-runtime-architecture-critique-part1.md`、`docs/reviews/audit/2026-05-08-runtime-architecture-critique-part2.md`
> 当前基线：12 包模块化架构，`arch-check` 36 kept / 0 broken，architecture smell check passed
> 目标：逐模块攻克架构与代码质量问题，在扩展性、理解性、可读性、一致性、整洁架构划分与优雅实现上追求卓越

## 1. 总体判断

当前 Ditto 的最大优势是**包结构和工程门禁已经站稳**：依赖方向、能力包拆分、跨包 re-export 治理、TYPE_CHECKING 清零、pandas 清零、Protocol-first 和 frozen dataclass 使用都达到优秀水平。

下一阶段不应继续做无行为收益的大规模搬文件，而应把 review 重心从“包边界是否干净”推进到三件事：

1. **运行时地基是否成立**：event/command/lifecycle、统一时间模型、状态恢复、OMS Lite、Backtest/Paper/Live 共享路径、continuous risk。
2. **领域概念是否归位**：reference / market_reference、DataCatalog runtime、消费者拥有 port、application 与 apps composition root 边界、研究层 port。
3. **代码是否长期可读可扩展**：命名唯一、public API 收敛、大文件和高 fan-in 拆解、异常入口统一、SQL/noqa 预算、E2E/golden data 证明力。

本计划采用“全局护栏 + 一个模块一个模块攻克”的方式。每个模块 review 都必须产出可验证证据，不只给主观意见；每个整改都必须以 TDD 和 `pixi run -e dev check` 收尾。

## 2. 当前源码快照

本次复核重新扫描了当前源码，关键数据如下：

| 包 | 文件 | 行数 | Protocol | dataclass/frozen | `Service` | `Provider` | 测试文件 | 当前主要压力点 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| kernel | 16 | 1,507 | 6 | 21/21 | 0 | 2 | 17 | 时间/事件太薄，trading/reference 语义有膨胀风险 |
| platform | 51 | 5,661 | 6 | 15/13 | 0 | 3 | 39 | `ParquetStore` 大文件，SQL/noqa 安全预算 |
| data | 270 | 30,691 | 20 | 50/50 | 14 | 11 | 166 | `Dataset` 路由、catalog runtime、reference 语义过重 |
| features | 105 | 14,629 | 23 | 80/80 | 5 | 4 | 33 | `services` 过宽，PIT/feature contract 需更声明化 |
| strategy | 48 | 5,325 | 13 | 51/50 | 2 | 2 | 28 | stage contract、benchmark 白名单、模板全球化 |
| portfolio | 21 | 1,717 | 11 | 23/22 | 0 | 0 | 15 | positions/holdings/target_portfolios 仍偏 contract/DTO |
| risk | 18 | 1,372 | 5 | 7/7 | 0 | 0 | 22 | continuous risk、状态恢复、集成覆盖不足 |
| execution | 35 | 2,983 | 10 | 22/20 | 2 | 2 | 19 | BrokerGateway 无实现，OMS/reconciliation 未闭环 |
| backtest | 31 | 4,686 | 6 | 26/24 | 0 | 0 | 37 | data-owned DataProvider，live/paper parity 不足 |
| analysis | 19 | 1,118 | 2 | 4/4 | 2 | 1 | 10 | application 直接 import research service，reserved namespace 成熟度 |
| application | 104 | 18,315 | 14 | 58/58 | 7 | 12 | 97 | providers 具体装配、Dataset routing、高 fan-in process |
| apps | 109 | 12,094 | 3 | 7/7 | 0 | 5 | 112 | composition root 边界、E2E skip、API/job 薄度 |

热点文件仍集中在 `data`、`application`、`features`、`backtest`、`platform`：最大文件包括 `data/sources/tushare/tushare_source.py`、`platform/foundation/storage/parquet_store.py`、`application/processes/ingestion/coordinator.py`、`data/services/market_service.py`、`features/expression/codegen.py`、`features/evaluation/evaluator.py`。

源码证据也确认了运行时缺口：

| 运行时概念 | 当前证据 | 判断 |
|---|---|---|
| `EventBus` | 生产 `subscribe` 仅在 kernel 定义，业务订阅流未形成 | 事件模型是 seam，不是中枢 |
| `TimeContext` | 0 命中；`knowledge_date`、`as_of_date`、`effective_from/to` 分散 | PIT 语义强，但没有统一时间上下文 |
| `DataProvider` | 33 命中，backtest 直接消费 data-owned Protocol | 需要消费者视角 DataPortal / narrow ports |
| `BrokerGateway` | 仅 Protocol 和占位 gateways namespace | 实盘 adapter / paper gateway / reconciliation 未闭环 |
| OMS identity | `ClientOrderId`、`BrokerOrderId`、`OrderJournal` 0 命中 | OMS Lite 还未成为一等模型 |
| `Dataset` | 494 字符串命中，75 文件 | 仍承担目录、调度、路由混合职责 |

## 3. 业界最佳实践取舍

本计划借鉴最佳实践，但不照搬大型平台复杂度。

| 实践来源 | 对 Ditto 的有效启发 | 本计划的落地边界 |
|---|---|---|
| Clean Architecture Dependency Rule | 源码依赖应指向内层，跨边界通过 port | 保持当前 12 包，不为“更像 DDD”大拆包 |
| Hexagonal Architecture | 应用可脱离 UI/DB 测试，外部设备经 adapter 接入 port | 只给跨边界、多实现或测试隔离需要的对话建 port |
| Python PEP 544 Protocol | 结构化子类型适合 Python ports | Protocol 要少而准，避免每个类前面都加仪式接口 |
| Import Linter | 架构约束必须机器化 | 把 Dataset 预算、suffix、empty namespace、public API 纳入 guard |
| NautilusTrader | message bus、component lifecycle、backtest/live shared kernel | 先做轻量 in-process event/command/lifecycle，不引入重型消息中间件 |
| QuantConnect LEAN | 回测与实盘共享语义，策略代码跨环境一致 | 先补 paper runtime 和共享 order/risk/brokerage seam |
| ArcticDB / 时间旅行数据 | PIT 应成为系统能力，不靠约定 | 先做 `TimeContext` 和 catalog time semantics，不先做完整时序数据库 |
| Polars Lazy API | 大表扫描应利用 predicate/projection pushdown | Data/Features 审核 lazy/materialize 边界，apps/application 不拉大表后过滤 |
| Test Pyramid | unit 底座强，高层测试证明关键路径 | 补 deterministic vertical slice，消除关键 E2E 对本地样本的跳过 |
| Twelve-Factor Config | 配置外置且集中在边界 | apps/composition root 读配置，领域包不读环境 |

参考资料：
- Clean Architecture: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- Hexagonal Architecture: https://alistair.cockburn.us/hexagonal-architecture/
- PEP 544 Protocols: https://peps.python.org/pep-0544/
- Import Linter contracts: https://import-linter.readthedocs.io/en/latest/contract_types.html
- NautilusTrader architecture: https://nautilustrader.io/docs/latest/concepts/architecture/
- QuantConnect LEAN algorithm engine: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine
- Polars Lazy API: https://docs.pola.rs/user-guide/concepts/lazy-api/
- Test Pyramid: https://martinfowler.com/bliki/TestPyramid.html
- Twelve-Factor Config: https://12factor.net/config

## 4. Review 方法论

每个模块按同一套流程审查，保证发现、整改和验收一致。

### 4.1 单模块 Review 标准流程

1. **证据包**
   - 读包级 `CLAUDE.md`、`pyproject.toml`、public `__all__`、最大文件、测试目录、import-linter 相关 contract。
   - 统计 LOC、Protocol、Service/Provider/Reader/Writer、异常类、noqa、public API、测试分布。

2. **七轴审查**
   - 依赖边界：是否只依赖允许包，是否存在软泄漏。
   - 领域归属：类型、函数、目录名是否表达唯一概念。
   - 抽象层级：同一文件是否混合 storage/source/use case/API/runtime。
   - Runtime 语义：事件、时间、状态、恢复、幂等是否足够。
   - 可读性：大文件、高 fan-in、后缀滥用、helpers/utils 逃逸。
   - 错误与可观测性：异常入口、错误码、trace/metric/journal 是否覆盖关键路径。
   - 测试证明：unit/integration/e2e 是否证明真实用户路径。

3. **分级**
   - P0：交易正确性、数据泄漏、运行时恢复、硬边界、虚假能力声明。
   - P1：模块扩展性、port 归属、composition root、目录 runtime 化、关键命名。
   - P2：public API 收敛、文件拆分、异常命名统一、observability 均衡。

4. **整改计划**
   - 每个发现必须有 “证据 -> 目标设计 -> RED 测试 -> GREEN 变更 -> REFACTOR -> 验证命令”。
   - 不接受只有“建议优化”的空洞条目。

5. **验收**
   - 模块测试通过。
   - 涉及依赖或架构边界时 `pixi run -e dev arch-check` 通过。
   - 完成阶段性整改后 `pixi run -e dev check` 通过。
   - 文档、CLAUDE、architecture guard 与源码一致。

### 4.2 全局 Review 产物

建议新增或维护以下产物：

| 产物 | 位置建议 | 用途 |
|---|---|---|
| 模块 review ledger | `docs/reviews/audit/module-review-ledger.md` | 记录每个模块的 open/accepted/fixed/deferred findings |
| 能力成熟度 manifest | `docs/architecture/capability-maturity.md` 或 YAML | 标明 production / initial-focus / experimental / reserved |
| 运行时决策 ADR | `docs/architecture/adr-runtime-spine.md` | 固化 event/command/time/state/OMS 的最小模型 |
| public API 清单 | 每包 `CLAUDE.md` 或 `docs/architecture/public-api.md` | 区分 stable public surface 与 internal implementation |
| 架构预算 guard | `scripts/architecture/check_architecture_smells.py` | Dataset 使用预算、suffix guard、empty namespace、public API budget |

### 4.3 分模块执行节奏

每个模块 review 按“准备 -> 证据 -> 判断 -> 整改 -> 验收”推进。不要跳过准备阶段直接写 finding，否则容易把跨模块问题误判成单包问题。

| 阶段 | 要做什么 | 最低产物 | 禁止 |
|---|---|---|---|
| 0. 准备 | 读本计划、包级 `CLAUDE.md`、相关架构规范、上一轮 review ledger | 当前模块 review brief | 只看最大文件就下结论 |
| 1. 证据 | 扫描 imports、LOC、public API、Protocol、Service/Provider、noqa、测试分布 | 证据表 + 热点文件列表 | 用主观印象替代源码位置 |
| 2. 判断 | 按七轴审查并分 P0/P1/P2/P3 | finding 表，含证据和风险 | 把所有不优雅都列成 P1 |
| 3. 设计 | 对 P0/P1 写目标设计、迁移边界、RED 测试点 | 模块目标设计小节 | 只写“建议重构” |
| 4. 整改 | 按 TDD 做最小变更，拆成可验证小 PR | 代码变更 + 测试 | 为清理而清理 |
| 5. 验收 | 跑模块测试、架构检查和全局 check | 验证命令输出摘要 | 未验证就关闭 finding |

单模块 review 建议控制在一个明确问题域内：例如 Kernel review 只冻结 runtime/time/reference 归属，不顺手修改 DataCatalog；Execution review 只定义 OMS Lite，不同时重写 Backtest loop。跨模块问题写入专项 ledger，由对应 wave 统一处理。

### 4.4 统一证据采集命令基线

以下命令从仓库根目录运行。模块名以 `<pkg>` 表示，例如 `kernel`、`data`、`application`；Python import 名以 `ditto_<pkg>` 表示，例如 `ditto_kernel`。每个模块可以追加专项命令，但不要少于这些基线。

```bash
# 目录、文件和测试分布
find packages/<pkg> -maxdepth 3 -type f | sort
find packages/<pkg>/tests -type f -name 'test_*.py' | sort

# 规模与热点
find packages/<pkg>/src -type f -name '*.py' -print0 | xargs -0 wc -l | sort -n | tail -20
rg -n "class .*Protocol|@dataclass|Service|Provider|Reader|Writer|Manager|Coordinator|Orchestrator|Registry|Catalog" packages/<pkg>/src packages/<pkg>/tests

# 边界与 public API
rg -n "^from ditto_|^import ditto_|__all__|TYPE_CHECKING|# noqa|type: ignore" packages/<pkg>/src packages/<pkg>/tests
rg -n "os\\.environ|getenv|Path\\(|open\\(|read_text|write_text|sqlite|duckdb|parquet|polars|pandas" packages/<pkg>/src packages/<pkg>/tests

# 模块验证
pixi run -e dev test packages/<pkg>/tests
pixi run -e dev arch-check
```

Review 报告必须把扫描结果压缩成结论，不粘贴长输出。建议记录：最大 10 个文件、跨包 import 摘要、public API 符号数、`noqa/type: ignore` 明细、测试缺口和无法自动判定的人工审查点。

### 4.5 Finding 编号与关闭规则

每条 finding 使用 `<PKG>-<Severity>-<NN>` 编号，例如 `DATA-P1-03`、`EXEC-P0-01`。状态只允许：

| 状态 | 含义 |
|---|---|
| open | 已确认问题，尚未设计或整改 |
| accepted | 已确认且有目标设计，等待实现 |
| fixed | 已整改并通过指定验证 |
| deferred | 明确不在当前 wave 处理，写清原因和重新评估条件 |
| rejected | 经证据复核不是问题，保留反证 |

关闭 `fixed` 必须同时满足：有源码或文档变更、对应测试或 guard 覆盖、模块测试通过；涉及跨包边界时还要 `arch-check` 通过。关闭 `deferred` 必须写出“为什么现在不做”和“什么信号出现时必须重开”。

## 5. 全局攻克顺序

推荐采用五个 wave。每个 wave 可拆成多个 PR，但不要跳过前置决策。

| Wave | 名称 | 目标 | 退出标准 |
|---|---|---|---|
| W0 | Baseline & Governance | 建立 review ledger、成熟度 manifest、运行时 ADR 草案、公共术语表 | 当前事实可追踪，后续 review 不再靠口头记忆 |
| W1 | Runtime Spine | kernel/execution/portfolio/risk/backtest/application 形成最小 event/time/state/OMS seam | 同一 order/risk/fill 状态流可在 backtest 和 paper 中复用并 replay |
| W2 | Reference & Data Spine | reference/market_reference 决策、DataCatalog runtime、Dataset enum 降权、DataPortal/consumer ports | 新增数据集/市场不再散改 enum + handlers + writer maps |
| W3 | Module Clarity | data/features/strategy/application/apps 大文件、高 fan-in、后缀、public API、reserved namespace 系统收敛 | 每包职责、public surface、命名和测试入口清楚 |
| W4 | End-to-End Proof | deterministic vertical slice + E2E fixtures + observability/journal | fast gate 不再跳过关键路径，报告链路可被重复验证 |

注意：W1 和 W2 有交叉。实现时可以按模块推进，但 review 时必须先冻结跨模块 contract，否则会在 execution/backtest/data 之间来回摆动。

## 6. 模块攻克计划

本节是逐模块执行卡。每个模块 review 都建议落地为 `docs/reviews/audit/modules/2026-05-08-<module>-review.md`，并把 finding 摘要同步到 `module-review-ledger.md`。如果某个模块发现的问题实质属于跨模块主题，只在本模块记录证据和影响，不在本模块强行设计全局解法。

### 6.1 Kernel

**当前定位**：最小共享语言，无外部依赖。

**核心问题假设**：
- `events.py` 只有 `DomainEvent(event_type: str, payload: dict[str, Any])`，不足以承载运行时 command/event/lifecycle。
- `clock.py` 只有 `now/today/advance_to`，无法表达 trade time、knowledge time、effective time、processing time。
- `trading.py` 承载 instrument definition / trading rule / fee schedule，未来可能更属于 reference/market_reference。

**Review 清单**：
- 审查 kernel 是否继续保持“跨全系统不可再分”的最小语言。
- 判断 `RuntimeEvent`、`RuntimeCommand`、`RuntimeLifecycle`、`TimeContext` 是否应在 kernel，还是 runtime/reference 包拥有。
- 审查 `Any` 使用：`DomainEvent.payload`、`FeeModel.order` 是否有可替代 typed payload。
- 审查 root barrel `__all__` 是否超过清晰上限。

**执行步骤**：
1. 先读 `packages/kernel/CLAUDE.md`、`packages/kernel/src/ditto_kernel/__init__.py`、`events.py`、`clock.py`、`trading.py`、`strategy.py`、`market.py`、`order.py`。
2. 扫描所有 `Protocol` 和值对象的跨包使用点，给每个类型标注“实际消费者”。只有至少两个核心平面长期需要的类型，才允许继续待在 kernel。
3. 对 `DomainEvent`、`Clock`、`InstrumentId`、trading/reference 相关类型做归属判断：保留、下沉到具体包、或进入 runtime/reference ADR。
4. 检查 kernel 是否仍满足零外部依赖、零 I/O、零业务流程；任何第三方 import 或存储/配置语义直接列为 P0/P1。
5. 对 root barrel 做 public API 预算：记录 `__all__` 数量、re-export 链深度、跨包实际导入路径。

**专项扫描**：
```bash
rg -n "Any|dict\\[str, Any\\]|event_type|payload|TimeContext|knowledge_date|as_of_date|effective_|processing|Runtime|Command|Lifecycle" packages/kernel packages/*/src packages/*/tests
rg -n "from ditto_kernel import|from ditto_kernel\\.[a-z_]+ import" packages/*/src packages/*/tests
pixi run -e dev test packages/kernel/tests
```

**必须产出**：
- `KERNEL-*` finding 表，至少覆盖 runtime event、time model、reference/trading、public API 四类判断。
- runtime/time/reference 归属 ADR 的 kernel 章节草案。
- kernel public API 清单，标注 stable / candidate / internal。

**验收标准**：
- 有一份 runtime/time/reference 归属 ADR。
- kernel 新增类型必须证明至少两个核心平面长期需要。
- 若保留 string event type，必须有 typed event registry 或 event name catalog。

### 6.2 Platform

**当前定位**：横切技术基础设施，只有异常继承 kernel 的精确豁免。

**核心问题假设**：
- `SQLiteStore` / storage table name 拼接依赖 `# noqa: S608`，需要白名单或 identifier registry。
- `ParquetStore` 文件较大，可能混合 pathing、schema、write mode、scan/materialize 逻辑。
- config/env 规则需要继续保证 application/domain 包不直接读取环境。

**Review 清单**：
- 审查所有 S608/noqa 是否有 table identifier 白名单、参数化 SQL、测试。
- 审查 foundation/storage 是否仍无业务语义。
- 审查 Polars LazyFrame / DataFrame 边界是否适合作为通用 storage contract。
- 审查 observability 基础设施是否能支撑 runtime journal id / trace id 贯穿。

**执行步骤**：
1. 先读 `packages/platform/CLAUDE.md`、`foundation/storage/**`、`config/**`、`observability/**`、`exceptions.py`。
2. 将所有 `S608`、SQL 字符串拼接、table name 插值分为：安全白名单、需要 identifier registry、应改参数化、误报。
3. 对 `ParquetStore` 按职责切片：pathing、schema validation、scan/lazy、write mode、metadata；只在职责混杂导致测试困难时建议拆分。
4. 检查 platform 是否出现 `dataset`、`strategy`、`instrument`、`order`、`trade` 等领域词；若只是日志文本可记录为 P3，否则判断是否越界。
5. 检查 config/env 入口：确认 application/domain 包没有通过 platform config 或 `os.environ` 绕过 apps composition root。

**专项扫描**：
```bash
rg -n "S608|SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|DROP TABLE|format\\(|f\\\".*\\{.*\\}" packages/platform/src packages/platform/tests
rg -n "dataset|instrument|strategy|order|trade|portfolio|risk|backtest" packages/platform/src
rg -n "trace|metric|span|journal|correlation|request_id|run_id" packages/platform/src packages/*/src
pixi run -e dev test packages/platform/tests
```

**必须产出**：
- SQL/noqa 明细表，含文件、行号、风险、建议 guard。
- storage 职责图，明确哪些拆分有行为收益，哪些只是机械拆分。
- observability 对 runtime journal / trace id 的能力缺口。

**验收标准**：
- SQL/noqa 有预算和 guard。
- Platform 不出现 dataset、instrument、trade、strategy 等领域词，除非在通用日志文本中。
- storage 大文件拆分只服务清晰职责，不做机械拆分。

### 6.3 Data

**当前定位**：数据平台，源码最大包，承担 sources/storage/services/quality/runtime/catalog/lineage。

**核心问题假设**：
- `Dataset` enum 仍混合数据目录、资产类别、日期调度、兼容方法。
- `DataCatalogEntry/DataCatalogReader/DataCatalogWriter` 只有 contract，没有 runtime store。
- data 同时承担 reference metadata、market data、source adapter、storage、quality，边界过重。
- `DataProvider` 由 data 定义并被 backtest/application 消费，消费者语言不纯。

**Review 清单**：
- 分析 Dataset 在 application、features、apps、tests 的实际使用，把使用点分为 compatibility、routing、domain logic、tests。
- 审查 catalog/lineage 是否能承载 schema/source/schedule/freshness/PIT metadata。
- 审查 source registry 是否足以新增数据源，不再扩展 union 或 handler branch。
- 审查 storage reader/writer CQRS，确认 Writer 的 `get_checksum` 例外是否应迁移。
- 审查 PIT：knowledge/effective/as_of 语义是否可以绑定到 `TimeContext`。
- 审查 lazy/materialize 边界，避免上层拉大表后过滤。

**执行步骤**：
1. 先读 `packages/data/CLAUDE.md`、`models/dataset.py`、`catalog/**`、`lineage/**`、`runtime/**`、`storage/**`、`sources/**`、`services/**`、`quality/**`。
2. 建 Dataset 使用矩阵：按 source/storage/quality/ingestion/application/apps/tests 分组，标注用途是目录事实、路由、兼容层还是测试 fixture。
3. 对 DataCatalog 做 runtime gap 分析：当前 contract、持久化 store、schema/freshness/source/time semantics、lineage ref、应用查询入口分别缺什么。
4. 选择 2 个新增数据集场景做 dry run：A 股 ETF 日线和一个非 A 股资产。记录需要修改的文件清单，用它衡量 Dataset enum 是否仍过重。
5. 检查 PIT 和 lazy 边界：上层是否先 materialize 再过滤，是否存在 `as_of`/`knowledge_date` 约定不一致。

**专项扫描**：
```bash
rg -n "Dataset\\.|Dataset\\(|dataset=|dataset_name|DataCatalog|CatalogEntry|Lineage|knowledge_date|as_of|effective_from|effective_to" packages/data packages/application packages/apps packages/features packages/backtest
rg -n "collect\\(|to_pandas|pandas|LazyFrame|scan_parquet|read_parquet|filter\\(" packages/data/src packages/features/src packages/application/src
rg -n "Fetcher|Source|Registry|Reader|Writer|get_checksum|schema|freshness|partition" packages/data/src packages/data/tests
pixi run -e dev test packages/data/tests
```

**必须产出**：
- Dataset 使用矩阵和降权路线，明确保留兼容层、迁移目标和预算。
- DataCatalog runtime MVP 设计，包含最小表/模型、读写 port、time semantics、lineage 关系。
- 新增数据集 playbook，从 catalog/spec 到 source/storage/quality/application 的最短路径。

**验收标准**：
- DataCatalog runtime MVP：至少可注册/list/get 数据资产，包含 source、schema、freshness、time semantics。
- Dataset 直接使用预算明确，application 直接路由使用目标降到 3 个文件以下。
- 新增数据集 playbook 只需 catalog/spec + source adapter + storage + quality + application facade，不散改多张 map。
- data-owned `DataProvider` 的未来命名和归属有迁移计划。

### 6.4 Features

**当前定位**：表达式、因子、衍生数据、物化、评估、发布安全。

**核心问题假设**：
- `features.services` 承载 derived catalog/query/artifact/gc/publication，领域子域不够显式。
- expression/materialization 边界已由 contract 守住，但 stage schema / requires / produces 仍不够声明化。
- feature PIT 与 publication safety 强，但未与统一 TimeContext/DataCatalog 打通。

**Review 清单**：
- 审查 `services` 是否应拆成 derived_catalog、derived_runtime、artifacts、publication。
- 审查 `codegen.py`、`evaluator.py`、metrics 文件是否按单一职责可拆。
- 审查表达式编译后的数据泄漏防护是否有统一测试模板。
- 审查 materialization manifest 是否记录 time semantics、input catalog refs、lineage refs。
- 审查 feature evaluation 是否只处理计算，不启动 data/application 流程。

**执行步骤**：
1. 先读 `packages/features/CLAUDE.md`、`contracts/**`、`expression/**`、`factors/**`、`materialization/**`、`evaluation/**`、`services/**`、`storage/**`。
2. 画内部依赖方向：contracts/models -> expression -> factors -> materialization -> evaluation -> services/storage，找反向 import 和跨层 convenience import。
3. 对 `services` 逐类分类：derived catalog、query、artifact、garbage collection、publication safety、runtime orchestration；判断是否需要拆子域或仅收敛 public API。
4. 选一个表达式因子和一个物化产物，追踪 input data -> expression -> manifest -> artifact -> publication 的 lineage 和 time semantics。
5. 检查 `codegen.py`、`evaluator.py` 和 metrics 热点是否承担多个抽象层；拆分建议必须绑定测试缺口或可读性风险。

**专项扫描**：
```bash
rg -n "from ditto_features\\.(expression|materialization|evaluation|services)|FeatureArtifact|Manifest|Publication|PIT|lookahead|closed=|knowledge|as_of|lineage|DataCatalog" packages/features packages/application packages/data
rg -n "collect\\(|shift\\(|rolling_|join_asof|forward_fill|backward_fill" packages/features/src packages/features/tests
rg -n "Service|Artifact|Catalog|Publication|Runtime|Evaluator|Codegen|Planner" packages/features/src packages/features/tests
pixi run -e dev test packages/features/tests
```

**必须产出**：
- features 内部依赖图和反向依赖 finding。
- feature artifact contract 草案：输入、时间语义、版本、lineage、发布状态。
- PIT 测试模板建议，至少覆盖 rolling、shift、join/asof、publication cutoff。

**验收标准**：
- 每个 feature artifact 能说明输入数据、时间语义、版本、发布状态。
- `features.services` 要么收敛 public API，要么拆成语义子域。
- 表达式/因子新增必须有 schema contract 和 PIT 测试。

### 6.5 Strategy

**当前定位**：策略定义与信号生成，不依赖 data/features/portfolio/risk/execution/backtest。

**核心问题假设**：
- Pipeline/Stage 清楚，但 `DecisionFrame` schema 还需要更明确的 requires/produces。
- `_KNOWN_BENCHMARKS` 和部分 stock/ETF 模板带 A 股阶段假设。
- `TargetPortfolio`、`SignalRecord` 等词需要和 portfolio/execution 生命周期消歧。

**Review 清单**：
- 审查所有 builtins/templates 是否只产生策略意图，不包含组合/执行/风控规则。
- 审查模板成熟度：A 股 ETF initial-focus vs stock/fx/commodity experimental。
- 审查 stage contract：input columns、output columns、empty behavior、error behavior。
- 审查 strategy storage services 是否更像 Store/Repository，是否需要命名调整。
- 审查 benchmark / universe / instrument language 是否应依赖 reference port。

**执行步骤**：
1. 先读 `packages/strategy/CLAUDE.md`、`alpha/**`、`pipeline/**`、`signals/**`、`templates/**`、`storage/**`、`di/**`。
2. 为每个 Stage 建 schema 卡：requires columns、produces columns、empty input、missing column、invalid value、time handling。
3. 扫描模板中的市场假设：ETF、stock、benchmark、calendar、交易日、涨跌停、费用、最小交易单位；把成熟度写入 maturity manifest。
4. 检查 strategy 是否只表达策略意图和信号，不隐含 portfolio sizing、risk reject、execution order state。
5. 审查 signal storage 命名：如果是物理读写，用 Store/Reader/Writer；如果是消费者需要的能力，用 Protocol/Port。

**专项扫描**：
```bash
rg -n "Stage|Pipeline|requires|produces|schema|DecisionFrame|SignalRecord|TargetPortfolio|benchmark|ETF|stock|calendar|limit|fee|lot|position|order|risk" packages/strategy packages/application packages/backtest
rg -n "from ditto_(data|features|portfolio|risk|execution|backtest)" packages/strategy/src packages/strategy/tests
pixi run -e dev test packages/strategy/tests
```

**必须产出**：
- Stage schema coverage 表，列出已有测试和缺口。
- 策略模板成熟度清单，进入 capability maturity manifest。
- strategy 输出词典，区分 signal / intent / target suggestion / execution order。

**验收标准**：
- 每个 Stage 有明确 schema contract 或测试证明。
- 策略模板标注市场/资产成熟度。
- 策略输出命名和 execution/portfolio target 生命周期清楚区分。

### 6.6 Portfolio

**当前定位**：组合、会计、持仓、调仓，纯领域模型。

**核心问题假设**：
- `holdings`、`positions`、`target_portfolios` 仍偏 Protocol/DTO，缺最小 runtime/store。
- Account/AccountView 设计好，但账户状态恢复、持仓快照、事件发布不足。
- `PositionReader` 与 application/execution 同名，跨包阅读成本高。

**Review 清单**：
- 审查 Account、OrderBook、CashBook、Position 是否可从 order/fill journal 重建。
- 审查 PositionChanged / PortfolioEvent 是否应该进入 runtime event stream。
- 审查 target portfolio、actual position、holding snapshot 的词典和生命周期。
- 审查 portfolio 是否仍保持不依赖 execution/risk/backtest/data/platform。

**执行步骤**：
1. 先读 `packages/portfolio/CLAUDE.md`、`accounting/**`、`positions/**`、`holdings/**`、`target_portfolios/**`、`rebalancing/**`、`events.py`。
2. 追踪状态来源：初始现金、订单、成交、费用、持仓快照、目标组合；标出哪些状态可重放，哪些只能从 snapshot 恢复。
3. 对 portfolio 事件做生命周期判断：哪些属于领域事件，哪些属于 runtime audit，哪些只是测试辅助。
4. 建 target/actual/holding/position 词典，和 strategy/execution/application 同名词逐一消歧。
5. 检查 portfolio 纯领域边界：不得读 storage、env、data source，不得直接知道 risk/execution/backtest 具体实现。

**专项扫描**：
```bash
rg -n "Account|OrderBook|CashBook|Position|Holding|TargetPortfolio|Snapshot|Journal|Event|Fill|Fee|Reader|Writer|Store" packages/portfolio packages/execution packages/backtest packages/application
rg -n "from ditto_(data|features|risk|execution|backtest|platform)" packages/portfolio/src packages/portfolio/tests
pixi run -e dev test packages/portfolio/tests
```

**必须产出**：
- portfolio state rebuild 图：journal-only、snapshot+journal、不可恢复边界。
- positions/holdings/target_portfolios 成熟度判断和最小 runtime/store 建议。
- 跨包 PositionReader / Position / Holding 命名消歧表。

**验收标准**：
- 定义 portfolio state snapshot / journal / restore 的最小方案。
- positions/holdings/target_portfolios 至少有一个最小可用 runtime 或明确 reserved maturity。
- 跨包 PositionReader 命名消歧。

### 6.7 Risk

**当前定位**：pre-trade、post-trade、constraints、exposure、drawdown。

**核心问题假设**：
- 风控目前更像 pre/post 装饰步骤，还不是 order submit/modify/fill 的持续守门人。
- 风控状态，如 drawdown peak NAV，缺持久化和恢复。
- `@traced` 和集成测试覆盖偏薄。

**Review 清单**：
- 审查 risk gate 应在 execution/backtest/paper runtime 的哪个阶段介入。
- 审查正常风控命中是否全通过返回值表达，不滥用异常。
- 审查风险状态是否可 snapshot/rebuild。
- 审查 risk event 是否进入 event journal，是否可 replay 验证。

**执行步骤**：
1. 先读 `packages/risk/CLAUDE.md`、`checks/**`、`constraints/**`、`exposure/**`、`drawdown/**`、`events.py`、`models.py`。
2. 列出所有 risk decision 类型：allow、resize、reject、lock、unlock、post-trade warning；确认正常业务分支用返回值，系统异常才抛异常。
3. 画 continuous risk gate：strategy intent -> portfolio target -> order submit/modify/cancel -> fill -> position update -> post-trade review。
4. 追踪状态型风控，如 drawdown peak NAV、exposure baseline、cooldown/lock 状态，判断 snapshot/rebuild 所需输入。
5. 检查 risk 与 portfolio 的依赖是否只依赖账户/订单视图，不引入 execution/backtest/data 语言。

**专项扫描**：
```bash
rg -n "Risk|Decision|Violation|Reject|Resize|Allow|Lock|Unlock|Drawdown|Exposure|Constraint|Snapshot|Event|traced|audit|journal" packages/risk packages/execution packages/backtest packages/application
rg -n "raise .*Risk|Exception|DittoError|from ditto_(execution|backtest|data|features|strategy)" packages/risk/src packages/risk/tests
pixi run -e dev test packages/risk/tests
```

**必须产出**：
- continuous risk gate 设计图，标注 backtest/paper/live 共用点和当前缺口。
- risk state snapshot/replay finding。
- risk decision 事件 contract 草案，包含可审计字段。

**验收标准**：
- 订单 submit/modify/fill 路径有 continuous risk gate 设计。
- risk decision、resize、reject、lock/unlock 有审计事件。
- 至少一个 backtest/paper integration 证明风险状态可重放。

### 6.8 Execution

**当前定位**：订单、成交、券商网关、审计、费用/规则，依赖 portfolio/platform，不依赖 risk/backtest。

**核心问题假设**：
- `Brokerage` / `BrokerGateway` 双端口清楚，但 gateway 无实现。
- `ClientOrderId`、`BrokerOrderId`、OrderJournal、幂等 submit/cancel/modify、partial fill contract 尚未形成。
- `reconciliation` 只有 `ReconciliationReport`，不是交易闭环。

**Review 清单**：
- 审查订单生命周期：intent -> order -> ticket -> broker order -> fill -> position。
- 审查 ID 模型、幂等键、状态机、非法状态转换异常。
- 审查 paper/mock gateway MVP，避免直接接真实券商。
- 审查 fill/reconciliation/audit 是否能支持 crash recovery。
- 审查 planner 中 A 股规则哪些应由 reference/rules provider 提供。

**执行步骤**：
1. 先读 `packages/execution/CLAUDE.md`、`orders/**`、`broker/**`、`fills/**`、`audit/**`、`reconciliation/**`、`planner/**`、`reality/**`。
2. 写订单生命周期表：intent、order request、client order id、broker order id、ticket、accepted、partially filled、filled、cancelled、rejected、expired。
3. 检查状态机和幂等性：submit/cancel/modify/query_fills 重试时是否可去重，非法状态转换是否有明确错误。
4. 审查 BrokerGateway / Brokerage / paper/mock gateway 角色，确认真实券商实现不会进入 backtest。
5. 追踪 audit/reconciliation 数据是否足以 crash recovery：journal 顺序、fill identity、broker snapshot、position reconciliation。

**专项扫描**：
```bash
rg -n "BrokerGateway|Brokerage|Gateway|ClientOrderId|BrokerOrderId|OrderJournal|OrderState|Fill|Ticket|Cancel|Modify|Reconciliation|Idempot|Audit|Paper|Mock" packages/execution packages/backtest packages/application
rg -n "from ditto_(risk|backtest|data|features|strategy|analysis)" packages/execution/src packages/execution/tests
pixi run -e dev test packages/execution/tests
```

**必须产出**：
- OMS Lite contract 草案，包含 identity、state machine、journal、fill、reconciliation。
- paper/mock gateway MVP 范围，明确不接真实券商。
- A 股交易规则归属表：execution reality、reference/rules provider、backtest simulation。

**验收标准**：
- OMS Lite contract：ClientOrderId、BrokerOrderId、OrderState、OrderJournal、FillEvent、ReconciliationRecord。
- paper/mock gateway 可以跑最小 submit/cancel/query_fills。
- 同一执行语义可供 backtest/paper runtime 复用。

### 6.9 Backtest

**当前定位**：回测 runtime、step chain、模拟成交、绩效统计、审计。

**核心问题假设**：
- `EngineLoop` 是回测专用，Live/Paper 无共享 runtime。
- `ProviderBackedDataFeed` 全量加载并直接依赖 data-owned `DataProvider`。
- 交易状态主要在内存 list/deque/account 中，恢复路径不足。

**Review 清单**：
- 审查 step chain 中哪些是 runtime 通用：data slice、strategy decision、planning、risk gate、brokerage、audit。
- 审查 `DataFeed` 是否应演进为 backtest-owned `HistoricalDataPortal` 或 runtime-owned `DataPortal`。
- 审查 replay/golden baseline 是否能覆盖 state/journal/recovery。
- 审查 as_of / lookback / benchmark / bar fingerprints 的 PIT 证明。

**执行步骤**：
1. 先读 `packages/backtest/CLAUDE.md`、`engine/**`、`runtime/**`、`steps/**`、`simulation/**`、`data_feed/**`、`reports/**`、`metrics/**`。
2. 将 EngineLoop step chain 拆成通用 runtime、backtest-only simulation、reporting 三类；只把真正跨 backtest/paper 的 seam 提到 runtime 讨论。
3. 追踪一次回测：data slice -> strategy input -> signal/intent -> portfolio planning -> risk -> brokerage/fill -> account update -> metrics/report。
4. 检查 DataProvider 归属：当前 data-owned port 使用点、backtest 实际需要字段、HistoricalDataPortal 目标接口。
5. 检查 PIT 和 replay：as_of、lookback、benchmark、bar fingerprint、manifest、journal、deterministic seed 是否能重建结果。

**专项扫描**：
```bash
rg -n "EngineLoop|Step|DataFeed|DataProvider|DataPortal|Historical|as_of|lookback|fingerprint|manifest|journal|replay|seed|Brokerage|Risk|Portfolio|Fill" packages/backtest packages/application packages/data packages/execution
rg -n "from ditto_execution\\.broker\\.gateways|real broker|gateway" packages/backtest/src packages/backtest/tests
pixi run -e dev test packages/backtest/tests
```

**必须产出**：
- Backtest/Paper shared runtime seam 草案，标注不做 live 的边界。
- DataProvider -> HistoricalDataPortal / runtime DataPortal 迁移路线。
- deterministic replay/golden baseline 缺口表。

**验收标准**：
- 提出 Backtest/Paper shared runtime seam，不要求一次实现 live。
- 回测状态可从 manifest + journal + records 重建或明确不可恢复边界。
- DataProvider 归属迁移路线清楚。

### 6.10 Analysis

**当前定位**：研究 control-plane，reports/diagnostics/experiments/screeners reserved。

**核心问题假设**：
- application 直接 import `ResearchArtifactService/ResearchCatalogService` 等 analysis service。
- reserved namespace 已诚实标注，但需要成熟度 manifest 防误用。
- research dataset 和 data catalog 语义需要明确边界。

**Review 清单**：
- 审查 application 是否应定义 `ResearchCatalogPort`、`ResearchArtifactPort`。
- 审查 analysis storage 是否只服务研究层，不混入生产数据目录。
- 审查 reserved namespace 是否有 guard，防止被当成 runtime API。
- 审查 research spec 与 DataCatalog spec 命名是否易混。

**执行步骤**：
1. 先读 `packages/analysis/CLAUDE.md`、`research/**`、`reports/**`、`diagnostics/**`、`experiments/**`、`screeners/**`、storage 相关实现。
2. 对 reserved namespace 做 use-site 扫描：任何 application/apps 对 reports/diagnostics/experiments/screeners 的行为依赖都列为 P1/P0。
3. 追踪 research dataset control-plane：spec、catalog、snapshot、artifact、storage；确认它不替代 production DataCatalog。
4. 检查 application 对 analysis service 的直接 import，判断应由 application-owned port 隔离，还是保持 research-only 豁免。
5. 把 analysis 能力成熟度写入 maturity manifest，避免全球全市场 product analysis 被误认为已实现。

**专项扫描**：
```bash
rg -n "Research|Artifact|Catalog|Snapshot|Spec|reports|diagnostics|experiments|screeners|reserved|future|DataCatalog|Dataset" packages/analysis packages/application packages/apps
rg -n "from ditto_analysis|import ditto_analysis" packages/{data,features,strategy,portfolio,risk,execution,backtest,application,apps}/src packages/*/tests
pixi run -e dev test packages/analysis/tests
```

**必须产出**：
- research vs production DataCatalog 边界说明。
- application-owned research ports 迁移计划或保留直接依赖的 ADR 条件。
- reserved namespace guard 建议和 maturity manifest 条目。

**验收标准**：
- application 不直接依赖 analysis service 语言，至少有迁移计划。
- reserved namespace 出现在 maturity manifest。
- research dataset 和 production data catalog 边界写入文档。

### 6.11 Application

**当前定位**：CQRS 用例编排与对象装配。

**核心问题假设**：
- `providers.py` 直接 import SQLiteClient、具体 reader/writer、data services、feature services、execution stores，像二级 composition root。
- ingestion 仍直接使用 Dataset 和 data source Fetcher Protocol。
- process/builders 高 fan-in，部分文件 500-760 行。

**Review 清单**：
- 审查 providers 是否只 wiring，具体实现是否应下沉 apps registry 或独立 composition。
- 审查 queries/commands/processes/builders R8 规则之外是否有软泄漏。
- 审查 ingestion coordinator/data_writer/fetch_handlers 中 Dataset routing 的替代路线。
- 审查 application-defined ports 是否覆盖 research、ingestion source、runtime data portal、manual execution。
- 审查 process 文件拆分是否按用例/阶段而非机械行数。

**执行步骤**：
1. 先读 `packages/application/CLAUDE.md`、`providers/**`、`builders/**`、`queries/**`、`commands/**`、`processes/**`、`config/**`。
2. 为 providers concrete imports 建预算表：storage/source/data service/feature service/execution store 是否只是 wiring，是否应移动到 apps registry 或独立 composition module。
3. 对 ingestion process 做 Dataset routing trace：coordinator、fetch handlers、data writer、quality、metadata、list date inference；找新增数据集散改点。
4. 审查 application-owned ports：research、ingestion source、runtime data portal、manual execution、notification；消费者需要什么就定义什么。
5. 对高 fan-in process/builders 做职责拆分判断：按流程阶段拆，而不是按行数机械拆。

**专项扫描**：
```bash
rg -n "from ditto_(data|features|strategy|portfolio|risk|execution|backtest|analysis|platform)|Provider|Builder|Coordinator|Orchestrator|Dataset|Fetcher|DataWriter|Research|Port|Protocol" packages/application/src packages/application/tests
rg -n "os\\.environ|getenv|SQLite|Parquet|Reader|Writer|Store|Source|Gateway|Service" packages/application/src
find packages/application/src -type f -name '*.py' -print0 | xargs -0 wc -l | sort -n | tail -20
pixi run -e dev test packages/application/tests
```

**必须产出**：
- application concrete wiring 预算和迁移路线。
- Dataset routing 散改点表，和 DataCatalog/DataPortal 目标替代路线。
- process/builders 高 fan-in 拆分建议，必须绑定一个用例阶段。

**验收标准**：
- application providers concrete imports 有预算和迁移路线。
- ingestion 新增数据集不再依赖多处 hard-coded branch。
- 每个 process 文件只表达一个流程阶段或一个装配职责。

### 6.12 Apps

**当前定位**：FastAPI、CLI、Prefect、composition root、配置加载。

**核心问题假设**：
- registry 作为 composition root 是合理豁免，但非 registry API/CLI/job 必须保持薄。
- E2E 只有 6 个文件，且关键 reporter 用例存在样本 skip。
- API/models 多市场能力存在，需要成熟度标注避免误解。

**Review 清单**：
- 审查 API route、CLI command、job flow 是否只调用 application facade/command/process。
- 审查 registry import capability 的范围是否最小。
- 审查 config loader 是否是环境读取唯一入口。
- 审查 E2E fixtures 是否可提交、可生成、可重复。
- 审查错误映射是否基于明确异常类型，不用字符串匹配。

**执行步骤**：
1. 先读 `packages/apps/CLAUDE.md`、`api/**`、`cli/**`、`jobs/**`、`registry/**`、`config/**`、`testing.py`。
2. 分开审查 registry 与非 registry：registry 可以 composition root 装配具体实现；route/CLI/job 只能调用 application facade/command/process。
3. 追踪环境配置入口：所有 env/config loader 应集中在 apps/config 或 composition root，领域包和 application 不散读环境。
4. 对 API/CLI/job 做薄度审查：参数解析、调用 application、错误映射、响应格式化之外的业务逻辑都列 finding。
5. 审查 E2E：找 skip 原因、本地样本依赖、fixture 可复现性、deterministic vertical slice 缺口。

**专项扫描**：
```bash
rg -n "from ditto_(data|features|strategy|portfolio|risk|execution|backtest|analysis)|Dataset|Service|Reader|Writer|Store|Source|Gateway|type\\(exc\\).__name__|str\\(exc\\)|skip|pytest\\.mark\\.skip" packages/apps/src packages/apps/tests
rg -n "os\\.environ|getenv|BaseSettings|Config|registry|provide|container|facade|Command|Query|Process" packages/apps/src packages/apps/tests
find packages/apps/src -type f -name '*.py' -print0 | xargs -0 wc -l | sort -n | tail -20
pixi run -e dev test packages/apps/tests
```

**必须产出**：
- registry 豁免边界清单，说明每个直连 import 是否必要。
- route/CLI/job 薄度 finding，含替代 application 入口。
- E2E fixture 和 deterministic vertical slice 补强计划。

**验收标准**：
- 非 registry 直连 capability 继续由 guard 控住。
- 关键 vertical slice E2E 不因本地样本缺失而跳过。
- API/CLI 不复制 Dataset 或 maturity 事实。

## 7. 跨模块主题专项

这些主题不能只归给一个包，需要在模块 review 间持续跟踪。

| 主题 | 牵涉模块 | 当前风险 | 目标 |
|---|---|---|---|
| Runtime event/command/lifecycle | kernel, execution, backtest, risk, application | EventBus write-only，事件 payload 无类型 | 可订阅、可审计、可 replay |
| TimeContext/PIT | kernel, data, features, backtest, execution | 时间语义分散 | trade/knowledge/effective/processing time 统一 |
| OMS Lite | execution, portfolio, risk, backtest, application | order identity/journal/reconciliation 不完整 | backtest/paper/live 共享订单状态语义 |
| Reference domain | kernel, data, execution, backtest, risk, portfolio | instrument/venue/calendar/rule 分散 | 最小 market_reference contract |
| DataCatalog runtime | data, application, features, apps | Dataset enum 主导 | catalog/spec/lineage/time semantics 主导 |
| Consumer-owned ports | application, backtest, features, analysis, data | 实现侧语言扩散 | 消费者定义窄 port，provider 只 adapter |
| Composition root | application, apps | application 知道具体 storage/source | apps/composition 拥有物理 wiring |
| Public API 收敛 | all packages | `__all__` surface 宽 | stable/internal 清楚 |
| Maturity manifest | all packages | 全球全市场与 A 股 ETF 初期能力混读 | production / initial-focus / experimental / reserved |
| E2E/golden data | apps, application, data, features, strategy, backtest, execution | 关键链路 skip | deterministic vertical slice |

## 8. Review 严重度与处理策略

| 严重度 | 定义 | 处理 |
|---|---|---|
| P0 | 可能导致数据泄漏、错误交易、状态不可恢复、边界破坏、虚假生产能力声明 | 当前 wave 内必须处理或写 ADR 明确不处理原因 |
| P1 | 降低扩展性、造成概念混乱、导致新增功能散改多个包 | 模块攻克时优先处理 |
| P2 | 命名、可读性、public API、异常入口、observability 均衡 | 进入模块 polish 阶段，不能无限积累 |
| P3 | 低收益整理或审美偏好 | 不进入近期整改，避免整理癖式改动 |

判断原则：只要一个问题会让下一个 agent 不知道代码该放哪里，至少是 P1；只要一个问题会让交易/回测结果无法证明正确，直接是 P0。

## 9. 每个模块的 Review 报告模板

后续逐模块输出报告建议统一格式：

```markdown
# <Module> Review Report

## 1. 当前职责与边界
## 2. 源码证据
## 3. 发现列表
| ID | 严重度 | 证据 | 风险 | 建议 |
## 4. 目标设计
## 5. TDD 整改计划
## 6. 验收命令
## 7. 延后项与原因
```

每条发现必须能回到源码位置、测试缺口或架构 contract；不能只有“感觉不优雅”。

## 10. 首批建议攻克顺序

如果从明天开始逐模块执行，推荐顺序如下：

1. **W0 全局基线**：建立 review ledger、maturity manifest、runtime ADR 草案、术语表。
2. **Kernel**：冻结 event/time/reference 最小语言边界，避免后续模块反复迁移基础类型。
3. **Execution**：定义 OMS Lite、order identity、journal、paper/mock gateway、reconciliation skeleton。
4. **Portfolio**：定义 state snapshot/rebuild、positions/holdings/target lifecycle。
5. **Risk**：把 risk gate 嵌入 runtime path，补 decision event 和状态恢复。
6. **Backtest**：抽 shared runtime seam，收敛 data portal、event journal、deterministic replay。
7. **Data**：推进 DataCatalog runtime，降低 Dataset enum 权重，明确 reference/data 边界。
8. **Features**：把 feature artifact、lineage、time semantics、publication safety 串起来。
9. **Strategy**：收紧 stage schema、模板成熟度和全市场扩展语言。
10. **Application**：迁移 concrete wiring，回收 consumer ports，拆高 fan-in processes。
11. **Apps**：补 deterministic E2E，确保 route/CLI/job 薄且 composition root 诚实。
12. **Analysis**：建立 research ports，固定 reserved namespace 成熟度。
13. **Platform**：在每个 wave 中穿插处理 SQL/noqa、observability、config guard；不单独做大重构。

这个顺序的理由是：运行时基础语言先定，交易状态语义随后定，再处理数据目录与用例编排。这样能减少“先拆 data/application，后面因为 runtime 语义改变又返工”的概率。

## 11. 近期可执行的第一步

第一步不直接改代码，先创建 W0 基线材料：

1. 建 `module-review-ledger.md`，列出 12 包 review 状态、负责人、P0/P1 数量、当前 wave。
2. 建 `capability-maturity.md`，标注 A 股 ETF 初期重点、stock/fx/commodity/macro 等能力成熟度。
3. 写 `adr-runtime-spine.md` 草案，回答：
   - event/command/lifecycle 类型归属在哪里？
   - `TimeContext` 是否进入 kernel？
   - OMS Lite 最小模型包含哪些对象？
   - Backtest/Paper shared seam 的边界是什么？
4. 为 architecture smell checker 设计下一批 guard：
   - Dataset direct usage budget
   - empty/reserved namespace maturity guard
   - Service/Manager suffix guard
   - public API `__all__` budget
   - S608/noqa SQL table identifier budget

完成 W0 后，再进入 Kernel review。Kernel review 不求一次写完整 runtime，只求把基础语言定准；这会让后面的 execution、portfolio、risk、backtest 可以沿着同一条路走。

## 12. 成功标准

当这一轮 review 和整改完成时，Ditto 应达到以下状态：

- 架构评分不只“包结构优秀”，运行时也有明确骨架。
- 新增市场、数据集、策略模板、paper gateway 不需要跨多个无关包散改。
- 每个领域词只有一个主语义，跨包同名有明确上下文限定。
- application 负责编排，不再知道过多物理 storage/source concrete。
- apps 是入口和 composition root，不承载业务规则。
- data catalog、reference、feature lineage、runtime journal、order state、risk decision 可以互相追踪。
- 关键用户路径有可重复 E2E/golden 证明。
- 每个包的 public API、reserved namespace、maturity 都清楚，后续 agent 不会误判能力边界。

一句话目标：**从“边界清楚的研究/回测框架”进化为“运行时语义清楚、领域归属准确、可持续扩展的模块化量化交易平台”。**
