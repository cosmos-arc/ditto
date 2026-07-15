# Ditto 当前架构综合评估报告

> 日期：2026-05-07
> 基准文档：`docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`
> 审计范围：重构后的 12 包能力架构、源码依赖、工程门禁、测试结构、可演进性
> 方法：旧发现回归验证 + AST/import 静态扫描 + `pixi run -e dev check` + 业界一手资料对标 + `2026-05-07-deep-architecture-evaluation.md` 证据整合

## 1. 执行摘要

当前 Ditto 架构已经从旧报告里的 `kernel / infra / data / analytics / engine / app / interfaces` 七包模型，完成重构为 12 包能力架构：

```text
apps -> application -> {data, features, strategy, portfolio, risk, execution, backtest, analysis} -> kernel
platform 为横向技术基础设施
```

总体判断：**架构重构成功，当前工程综合评分 86/100（8.6/10）**。核心提升不只是目录拆分，而是依赖方向、语义所有权、CQRS 编排、跨包 re-export 治理、Platform 去业务化、Features/Strategy/Execution/Backtest 分平面隔离等约束已经由机器门禁固化。

本报告采用的主原则是：**Ditto 是面向 research/backtest/execution/data 的模块化量化系统，不是传统 DDD 示范工程**。DDD 的价值在这里是借鉴边界划分、统一语言、子域治理和上下文关系，不作为架构目标本身，也不意味着要做微服务化、大拆包或完整 DDD 战术模式。

如果只按“正确性、合理性、10/10 理想领域边界”打分，不考虑改造成本，当前命名、抽象边界和领域划分专项约为 **7.4/10**。主要扣分不是依赖规则，而是 Data 包承担了过多 reference/market/data-catalog/source/storage 语义，application 核心仍接触较多具体装配细节，部分 port 不是消费者拥有，且全球全市场所需的 reference domain、catalog runtime、lineage、OMS/reconciliation 成熟度还没有完全闭环。

`2026-05-08-runtime-architecture-critique-part1/part2.md` 补充了一个关键盲点：前述 8.6 主要是**包结构与工程质量评分**，不是完整的**运行时架构评分**。按模块化量化系统的运行时地基看，当前约 **6.4/10**；按全球全市场 live-ready 架构看，当前约 **5.0/10**。主要差距是 EventBus 基本没有订阅流、BrokerGateway 无实现、backtest/live 没有共享 runtime、交易状态恢复不足、统一时间模型和流式数据能力尚未形成。

最主要的剩余风险集中在四处：

1. `Dataset` enum 仍然是应用编排层的核心路由语言，DataCatalog 目前只有契约，尚未成为真正运行时目录。
2. E2E 覆盖仍偏少，且 25 个 reporter E2E 用例因 TDX 样本数据缺失被跳过。
3. 产品定位是全球全市场量化系统，初期能力重点在 A 股 ETF；源码中的 stock/fx/commodity/macro 等多域能力符合长期方向，但需要标清成熟度，避免把“已建基础能力”误读成“当前生产能力全量可用”。
4. 运行时地基还不够：当前更像组织良好的批处理研究/回测框架，还不是 backtest/paper/live 共用 runtime 的交易系统。

## 2. 当前源码快照

| 指标 | 当前值 | 评价 |
|---|---:|---|
| 生产源码文件 | 827 | 12 包拆分后文件数增加，但边界更清楚 |
| 生产源码行数 | 100,085 | 规模略大于旧评估，复杂度主要分布在 data/application/features/apps |
| 测试 Python 文件 | 664 | 覆盖面强 |
| `test_*.py` 文件 | 595 | unit 主导，integration/e2e 偏少 |
| `Protocol` | 119 | 符合 Python 结构化子类型和 Ports 思路 |
| `ABC` | 2 | 比旧报告更克制 |
| frozen dataclass | 356/364 | 不可变数据模型默认化，优秀 |
| `# type: ignore` | 0 | 优秀 |
| `TYPE_CHECKING` | 0 | 优秀，未用延迟导入掩盖循环依赖 |
| pandas import | 0 | 符合项目约束 |
| import-linter 合约 | 36 kept, 0 broken | 强边界治理 |
| architecture smell check | passed | Platform 领域泄漏、re-export 等已纳入门禁 |
| `pixi run -e dev check` | passed | 6273 passed, 25 skipped |

源码体量分布：

| 包 | 文件 | 行数 | 主要评价 |
|---|---:|---:|---|
| data | 270 | 30,690 | 最大包，storage/source/service 仍是导航主成本 |
| application | 104 | 18,315 | 编排层清晰，但 ingestion/runtime builder 仍偏大 |
| features | 105 | 14,625 | 表达式、物化、发布安全职责已迁回 features |
| apps | 109 | 12,094 | 传输层和 composition root 分离较好 |
| strategy | 48 | 5,321 | 已脱离 data/features/portfolio/risk/execution/backtest |
| backtest | 31 | 4,686 | 依赖组合合理，回测 runtime 已独立 |
| platform | 51 | 5,661 | Platform 领域语义泄漏已清理 |
| kernel | 16 | 1,507 | 仍保持小核心 |

### 2.1 深度报告证据整合

`2026-05-07-deep-architecture-evaluation.md` 的最大价值是逐包证据密度高。综合采纳其源码观察后，当前最有判断力的证据如下：

| 包 | 深度报告中的有效证据 | 本报告采纳后的判断 |
|---|---|---|
| kernel | 外部依赖为 0，21/21 dataclass frozen，Protocol 很少 | 小核心质量高；但 `trading/quality/research/publication_safety/strategy` 记录继续增长会把 kernel 推向共享杂物层 |
| platform | 业务语义泄漏已由 smell checker 清零，config/env 读取集中 | 技术基础设施边界正确；`SQLiteStore` 表名 SQL 拼接的 `noqa` 仍应专项治理 |
| data | `SourceRegistry` + 5 个 Fetcher Protocol、Reader/Writer CQRS、UnitOfWork、data architecture tests 都很强 | 数据平台工程能力强；但它同时承担 reference metadata、market data、source、storage、catalog/lineage contract，领域重心偏重 |
| strategy | 零依赖 data/features/portfolio/risk/execution/backtest，pipeline stage 结构干净 | 策略包边界优秀；但 benchmark 白名单和部分 backtest 命名仍带阶段性市场假设 |
| portfolio | Account/AccountView、OrderTicket immutable-with、report view Protocol 设计好 | 纯领域模型优秀；holdings/positions/target_portfolios 还停留在 DTO/Protocol 层 |
| risk | CompositePreTradeCheck 和 resize/recheck 测试严谨 | 风控方向正确；规则体系、异常层级、trace/integration 覆盖仍偏薄 |
| execution | `Brokerage` vs `BrokerGateway` 双端口清楚，planner 覆盖 A 股规则 | 执行边界正确；OMS、真实 gateway、reconciliation 还不是生产闭环 |
| backtest | step chain、ReplayValidator、`as_of_date <` 防前瞻、golden baseline 是强证据 | 回测 runtime 成熟度高；仍依赖 data-owned `DataProvider`，live/backtest parity 尚未完全证明 |
| analysis | production packages 不依赖 analysis，reserved namespace 有明确 docstring 与 `__all__=[]` | 研究层隔离正确；application 仍直接 import analysis service，应改为消费者 port |
| application/apps | R8 CQRS kept，apps registry 作为 composition root，测试层次完整 | 编排方向正确；application providers 和 research/data concrete wiring 仍让 application 核心知道太多外层细节 |
| features | 纯 Polars DataFrame 测试、expression/materialization 隔离 kept | 计算层质量强；`services` 过宽，derived catalog/runtime/publication 应进一步显式分域 |

横切证据也值得纳入：

- Protocol 分布健康但不完美：features 23、data 20、application 14、strategy 13、portfolio 11、execution 10；约 80% 符合消费者定义 port，剩余集中在 `DataProvider`、data Fetcher Protocol、analysis research services、platform ABC。
- 测试金字塔底座强：`test_*.py` 里 unit 525、integration 55、e2e 6、registry 8、benchmark 1；这支持工程质量高分，也支持 E2E 证明力不足的扣分。
- 异常体系统一根较好：全库约 78 个异常类最终归到 `DittoError`；但 `errors.py` / `exceptions.py` 混用，命名一致性不足。
- public surface 过宽是事实：AST 口径下 537 个 `__all__` 定义、1963 个字面导出符号；跨包 re-export 清零不等于 public API 已收敛。

### 2.2 新增源码复核意见的采纳与校正

后续新增的一份源码复核意见总体方向与本报告一致：Ditto 的包边界、机器门禁和工程治理已经很强，真正短板正在从“架构是否清楚”转向“交易 runtime 和产品闭环是否成立”。其中有几条值得纳入，但也有部分判断需要按当前源码校正：

| 复核意见 | 本报告判断 | 处理 |
|---|---|---|
| 最新 100 分 review 记录显示 `pixi run -e dev ci` 最终通过，`6775 passed, 126 skipped`，coverage 93.37% | **采纳为文档证据**。这是 `docs/reviews/2026-05-04-capability-architecture-100-point-review.md` 中记录的 CI 结果；本报告本次实际验证仍采用 `pixi run -e dev check` 的当前本地输出 | 支持 8.6 工程综合分，但不改变 runtime/live-ready 扣分 |
| “架构治理强于产品/runtime 闭环” | **采纳**。这句话比“继续架构清理”更准确地描述下一阶段风险 | 已体现在第 9、10、11 节：P0 转为 runtime 地基 |
| 下一阶段应叫 **OMS Lite**，而不是“接一个券商” | **强采纳**。真实 broker adapter 之前必须先有 order identity、order journal、幂等、partial fill contract、broker event reconciliation | 纳入 P0/P2：Backtest/Paper/Live shared seam 必须带 OMS Lite contract |
| DataProvider 应演进为 DataPortal | **采纳但改写**。不建议把 data-owned `DataProvider` 直接扩大成平台门面；更好的做法是由 backtest/runtime/application 拥有消费者视角的 `DataPortal` port，data 只提供 adapter | 纳入 P1 consumer-owned ports |
| DecisionFrame schema 仍纯隐式、无运行时校验 | **部分过时**。当前已有 `FrameCol` 和 `validate_frame`，内置 stage 已使用必需列校验；但 `pipeline.py` 顶部文档仍写“不做运行时 schema 校验”，且还缺声明式 requires/produces contract | 作为文档漂移和 stage contract 改进项保留，不再作为重大架构缺口 |
| 前端工作台 4.8/10 | **无法在本仓库充分验证**。`ditto-app` 是独立仓库，本报告只评估后端仓库；该意见可作为产品路线图参考 | 不纳入后端架构评分，只在产品成熟度上作为外部提醒 |
| 不要继续大拆包，保持 12 包 | **原则采纳**。不能为了 DDD 大拆包；但 `reference`/`market_reference` 若作为包内 context 或独立能力边界，仍是全球全市场系统的合理演进，不等于微服务化 | 保持“最小能力边界 + 机器门禁”，避免整理癖式搬文件 |

## 3. 旧评估发现回归

| 旧 ID | 旧问题 | 当前状态 | 评价 |
|---|---|---|---|
| F01 | import-linter 线性合约与 diamond 模型矛盾 | **已解决** | `.importlinter` 明确说明 layers 是工具表达，平面隔离由 forbidden contracts 固化 |
| F02 | Dataset StrEnum 泄露 | **部分解决** | apps 普通代码已基本隔离，但 application 仍有 12 个文件、约 245 处 `Dataset` 命中；DataCatalog 仅契约化 |
| F03 | Exchange enum 重复 | **已解决** | source exchange 语义已归 data source normalization |
| F04 | StrategyRunService 同名 | **已解决** | strategy run 生命周期和 storage 语义更清楚 |
| F05 | CQRS Reader/Writer 纯度 | **基本解决** | 未发现 Reader 写方法；Writer 仅剩 8 处 `get_checksum` 这类读式辅助方法 |
| F07 | expression 依赖 materialization | **已解决** | `features.expression` 禁止依赖 `features.materialization` 合约 kept |
| F09 | tracing 覆盖不足 | **改善** | 59 个文件含 `@traced`，且 kernel trace bridge 到 apps registry |
| F10 | E2E 测试偏少 | **仍存在** | 6 个 E2E `test_*.py` 文件，fast check 中 25 个 reporter E2E 用例因样本缺失跳过 |
| F12 | 约定无法机器强制 | **显著改善** | architecture smell checker 覆盖 17 类语义 smell |
| F13 | Data 包导航成本高 | **仍存在但降低** | Data 从旧架构 43% LOC 降到当前约 31% LOC，但仍是最大包 |
| F14 | 超大文件 | **已解决** | 当前最大文件 777 行，低于 smell checker 800 行门槛 |

## 4. 评分卡

| 维度 | 权重 | 得分 | 说明 |
|---|---:|---:|---|
| 依赖边界与架构清晰度 | 18% | 9.3 | 36 条合约全绿，生产包不依赖 analysis，strategy/execution/backtest 边界明确 |
| 模块化与语义所有权 | 14% | 8.8 | Platform 去业务化、features 发布安全归位；DataCatalog 尚未运行时落地 |
| Ports/Adapters 与 DI | 12% | 8.7 | 119 个 Protocol，apps registry 作为 composition root；少数 port 仍由实现侧语言影响 |
| CQRS 与 application 编排 | 10% | 8.8 | R8 queries/commands/builders 互斥全绿，process 仍存在大文件和高 fan-in |
| 数据架构、PIT 与目录治理 | 12% | 8.0 | PIT/storage 测试强，catalog/lineage 只有 contract，Dataset enum 仍承担运行时目录职责 |
| 量化平台研究-回测-执行一致性 | 10% | 7.8 | 回测闭环较完整，live broker gateway/OMS/reconciliation 仍是骨架或待完善 |
| 工程质量与验证 | 12% | 9.2 | `check` 全绿，type/ruff/test/arch gate 强；E2E 数据依赖导致 25 skip |
| 可观测性与运维 | 6% | 8.3 | OTel bridge、metrics catalog、notification 已清理；关键路径覆盖还可系统化 |
| 可理解性与 agent 友好度 | 6% | 8.6 | 包级 CLAUDE、边界文档、smell guard 好；data/application 大文件仍增加认知成本 |
| **综合** | **100%** | **8.6/10** | 进入优秀区间，但还不是“满分架构” |

补充口径：上表是工程综合质量评分，包含已实现门禁、测试和当前可运行性。若按 10/10 理想领域模型只看“命名是否唯一、抽象是否纯、领域边界是否最合理”，专项分应采用第 8 节的更严格口径：**7.4/10**。

与 2026-04-28 旧评估对比：

| 维度 | 旧评估 | 当前评估 | 变化 |
|---|---:|---:|---|
| 架构能力 | 7.0 | 8.8 | +1.8 |
| 工程质量 | 7.5 | 9.2 | +1.7 |
| 业务/产品闭环 | 3.5 | 6.8 | +3.3 |
| 可演进性 | 7.5 | 8.6 | +1.1 |
| 可理解性 | 7.2 | 8.6 | +1.4 |
| **综合** | **约 7.0** | **8.6** | **显著提升** |

## 5. 业界最佳实践对标

### 5.1 Clean Architecture

Robert C. Martin 的 Dependency Rule 要求源码依赖只能指向内层，高层策略不应知道外层细节，并通过依赖倒置跨边界通信。Ditto 当前的 `kernel` 小核心、能力包隔离、`application` 编排和 `apps` 传输适配基本符合这个方向。尤其是 `strategy` 不依赖 `data/features/portfolio/risk/execution/backtest`，`execution` 不依赖 `risk/backtest`，比旧架构更接近“内层策略不认识外层实现”。

不足是 Data 的 `Dataset` enum 仍向 application 扩散。它不是严重边界违规，但它使编排层必须知道 Data 内部目录枚举，离“内层方便的数据结构跨边界传递”还有一步距离。

来源：Clean Coder, “The Clean Architecture” dependency rule: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html

### 5.2 Hexagonal / Ports & Adapters

Alistair Cockburn 原文强调应用应能脱离 UI 和数据库测试，外部设备通过 adapter 接入 port。Ditto 当前的 `apps` 普通模块只通过 application facade/command/process，registry 作为 composition root 才允许接触具体 provider，这个方向正确。`Brokerage` 与 `BrokerGateway` 的职责也已通过文档和测试区分：前者面向 backtest/live runtime loop，后者面向券商 adapter。

不足是部分 capability port 仍未完全“消费者拥有”，以及 live gateway/OMS 仍未完整落地。换句话说，端口语言已经有了，真实 adapter 生态还没长全。

来源：Alistair Cockburn, “Hexagonal Architecture the original 2005 article”: https://alistair.cockburn.us/hexagonal-architecture/

### 5.3 Python Protocol / Structural Typing

PEP 544 的目标是为 Python 提供静态结构化子类型支持，使无需显式继承也能满足接口契约。Ditto 当前 119 个 Protocol、仅 2 个 ABC，和 Python idiom 很契合。相较旧报告的 83 个 Protocol，当前跨包拆分后并没有退回继承树，而是继续用结构化契约保持替换性。

风险是 Protocol 数量增长后需要持续治理命名和归属，否则 port 会变成“每个文件都定义一点接口”。目前 import-linter 和 contract tests 能约束方向，但不能完全判断 port 是否过细。

来源：PEP 544: https://peps.python.org/pep-0544/

### 5.4 Import Linter 与机器化架构门禁

Import Linter 官方支持 `layers`、`forbidden`、`acyclic_siblings` 等 contract 类型。Ditto 当前做得比较成熟：用 `layers` 表达大方向，用 explicit `forbidden` 表达并列能力平面的互斥，用 `acyclic_siblings` 查循环，再用自研 smell checker 补足语义类 smell。

这是当前架构最接近“业界优秀工程化实践”的部分。建议下一阶段继续把 Dataset 迁移、Writer 查询方法、E2E 数据依赖也转成可执行门禁。

来源：Import Linter contract types: https://import-linter.readthedocs.io/en/latest/contract_types.html

### 5.5 量化平台对标：LEAN / NautilusTrader / FinRL-X

QuantConnect LEAN 强调开源、模块化、可插拔、backtest/live trading，并使用 streaming analysis 减少 look-ahead bias。NautilusTrader 进一步强调 research/backtest/live 共用执行语义和确定性时间模型。2026 年 FinRL-X 论文也把“模块化 + research/deployment consistency + broker execution 统一协议”作为量化平台方向。

Ditto 当前的优势：

- 能力包拆分比 LEAN 的大单体目录更清楚；
- PIT、安全物化、strategy/backtest/execution/risk 分离比普通 research notebook 工程更强；
- Protocol + DI 让 backtest/live 统一有了基础。

Ditto 当前的差距：

- live trading adapter、OMS、reconciliation 仍不完整；
- E2E/golden 数据闭环还不足以证明 research-to-live parity；
- 产品定位是全球全市场量化系统，A 股 ETF 是初期能力重点；源码保留 stock/fx/commodity/macro 多域能力与长期方向一致，但需要更清晰的成熟度标注。

来源：

- QuantConnect LEAN algorithm engine: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine
- QuantConnect/Lean repository: https://github.com/QuantConnect/Lean
- NautilusTrader overview: https://nautilustrader.io/docs/latest/concepts/overview/
- FinRL-X arXiv: https://arxiv.org/abs/2603.21330

### 5.6 Polars 与数据处理

Ditto 没有 pandas import，符合项目约束。Polars 官方建议在多数非探索场景优先 Lazy API，因为它支持 predicate/projection pushdown，减少内存和 CPU 负担。当前 Ditto 已经是 Polars-first，但建议把 lazy query plan 的边界更明确地写入 Data/Features 规则：存储扫描和大规模特征计算应优先使用 lazy/pushdown，application/apps 不应 materialize 大表后再过滤。

来源：Polars Lazy API: https://docs.pola.rs/user-guide/concepts/lazy-api/

### 5.7 测试金字塔

Martin Fowler 对 Test Pyramid 的核心观点是自动化测试应有更多低层测试，高层测试作为第二道防线。Ditto 当前 unit 测试非常充足，符合金字塔底座，但 E2E 只有 6 个 `test_*.py`，且样本数据缺失导致 25 个 reporter E2E 用例跳过。对架构而言，这意味着“模块级正确性”很强，“完整业务路径可证明性”仍偏弱。

来源：Martin Fowler, Test Pyramid: https://martinfowler.com/bliki/TestPyramid.html

### 5.8 配置与环境

Twelve-Factor 建议把部署间变化的配置放在环境中，并和代码分离。Ditto 当前 `os.environ` 主要集中在 platform/data/apps，application provider 禁止直接读环境变量，方向正确。后续要确保 Data source credential、Prefect/notification 等部署配置继续只在边界层读取，不流入领域包。

来源：The Twelve-Factor App Config: https://12factor.net/config

### 5.9 模块化量化架构、DDD 借鉴与过度设计边界

Ditto 的目标不是成为传统 DDD 架构，而是成为模块化量化系统：数据、特征、策略、组合、风控、执行、回测、研究各自有清晰能力边界，并通过 application/apps 进行编排和装配。DDD 在这里只作为边界划分工具借鉴：Martin Fowler 对 Bounded Context 的解释强调，在大模型中应把不同语言和模型显式切开，并说明它们之间的关系。Microsoft 的 DDD 指南也提醒，DDD 技术模式适合复杂且有显著业务规则的领域，重点不是套模式，而是让代码按业务问题和统一语言组织。Fowler 的 YAGNI 原则则提醒，不应只因为预想未来需要就提前实现能力。

因此，本报告的 10/10 建议应先满足模块化量化系统的现实公式，再借鉴 DDD 边界语言。满足以下三条才算不过度设计：

1. 领域语言已经混淆，继续不拆会增加错误放置概率；
2. 至少两个核心平面长期共享同一概念或规则；
3. 先建立最小可行边界、contract、adapter seam 和门禁，不提前实现完整产品能力。

来源：

- Martin Fowler, Bounded Context: https://martinfowler.com/bliki/BoundedContext.html
- Microsoft, Designing a DDD-oriented microservice: https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/ddd-oriented-microservice
- Martin Fowler, Yagni: https://martinfowler.com/bliki/Yagni.html
- Team Topologies, Thinnest Viable Platform: https://teamtopologies.squarespace.com/key-concepts-content/what-is-a-thinnest-viable-platform-tvp

### 5.10 交易系统架构参照

NautilusTrader 的公开文档把多资产、多 venue、research/backtest/live 统一执行语义作为核心目标，并显式建模 execution、portfolio、risk、adapter、OMS、venue position mode 等概念。LEAN 也把 backtest/live、brokerage、security/exchange hours、fee/fill/slippage plugin points 作为长期架构基础。对 Ditto 来说，这说明 `reference/market_reference`、execution OMS/reconciliation、backtest/live parity 不是纯学院派 DDD；它们是全球全市场交易平台会自然遇到的真实复杂度。

但 Nautilus/LEAN 也说明另一个边界：复杂 execution/order-book/OMS 能力应随真实交易场景逐步落地，不应为了“像成熟平台”而提前复制完整引擎。

来源：

- NautilusTrader overview: https://nautilustrader.io/docs/nightly/
- NautilusTrader execution: https://nautilustrader.io/docs/latest/concepts/execution/
- QuantConnect LEAN trading/orders: https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/trading-and-orders

## 6. 当前优点

1. **边界已机器化**：36 条 import-linter 合约、17 类 smell guard、边界单测共同工作。
2. **Platform 去业务化完成度高**：旧审计里最高优先级的 platform 领域泄漏已被 smell checker 清零。
3. **能力包隔离清晰**：strategy、portfolio、risk、execution、backtest 的依赖方向符合当前文档和 AGENTS 约束。
4. **Features 归位**：derived publication safety、shadow publication、factor evaluation 等语义已归 features，不再挂在 data/runtime。
5. **Application CQRS 可验证**：queries/commands/builders 互斥合约 kept，process 承担长流程。
6. **Python 类型实践强**：`TYPE_CHECKING`、`type: ignore`、pandas 均为 0，Protocol/immutable dataclass 使用成熟。
7. **工程门禁强**：`pixi run -e dev check` 全绿，fast suite 规模已经到 6273 passed。

## 7. 剩余风险

### R1. Dataset 仍承担运行时目录职责

`ditto_data.models.common.Dataset` 仍包含 asset class、date schedule、dataset list、兼容方法。Application 有 12 个文件直接消费 Dataset，尤其 ingestion coordinator、data_writer、fetch_handlers。DataCatalog 已存在 `DataCatalogEntry/DataCatalogReader/DataCatalogWriter`，但还没有 runtime implementation，也没有替代 Dataset 成为统一目录。

风险：新增数据集时仍需改 enum、fetch handler、writer mapping、coordinator 分支，扩展路径不够插件化。

### R2. E2E 和 golden data 证明力不足

当前 595 个 `test_*.py` 中，unit 525、integration 55、e2e 6。fast check 通过，但 25 个 E2E reporter 用例因 TDX 样本缺失跳过。

风险：架构边界强，但“数据摄取 -> 质量 -> 特征/策略 -> 回测 -> 手工执行/报告”这条用户路径的连续证明还不够稳定。

### R3. 全球全市场定位与阶段能力成熟度需要更清楚

项目定位是全球全市场量化系统，A 股 ETF 是初期能力重点。源码保留 stock、index、fx、commodity、macro、fundamental、capital 等能力与长期方向一致，不是产品边界冲突。真正的风险是成熟度标注不足：后续 agent 可能把已经存在的基础设施、研究能力、历史能力或薄骨架误判为“当前生产级全市场能力”。

### R4. Data/Application 大文件仍影响维护

当前最大文件低于 800 行门槛，但 `tushare_source.py`、`parquet_store.py`、`ingestion/coordinator.py`、`market_service.py`、`features/expression/codegen.py`、`features/evaluation/evaluator.py` 等 700 行级文件仍多。它们不是坏味道红线，但会提高 review 和 agent 修改成本。

### R5. 占位能力包还没有完全产品化

Portfolio holdings/positions/target_portfolios 已有 Protocol/DTO，但多数还只是契约；Execution gateways/reconciliation 仍是薄骨架；Analysis 的 reports/diagnostics/experiments/screeners 是 reserved namespace。当前 smell checker 已防止文档夸大能力，但产品闭环仍需填充。

### R6. Public API 面过宽

全仓有 537 个 `__all__` 定义、1963 个字面导出符号。跨包 re-export 已被 guard 清理，但包内 public surface 仍可能偏宽。长期建议把 stable public API 和 internal implementation 更明确地区分。

### R7. Application 仍穿透 analysis/data 实现侧语言

深度报告补充了两类此前没有展开的软泄漏：application 直接 import `ResearchArtifactService/ResearchCatalogService/ResearchDatasetSpec`，以及 ingestion process 直接使用 data-owned `MetadataFetcher/MarketFetcher` 等 Fetcher Protocol。Import-linter 允许 application 编排各能力包，但按 10/10 port 归属看，application 应定义 `ResearchCatalogPort`、`ResearchArtifactPort`、`IngestionDataSourcePort` 这类消费者语言，由 analysis/data 提供 adapter。

### R8. Service 后缀和异常文件命名需要治理

32 个生产 `*Service` 中，深度报告按职责归类后指出约 44% 更像 Store/Repository，例如 `ResearchCatalogService`、`TradeService`、`DerivedCatalogService`、`IngestionLogService`。这不是运行错误，但会降低领域语言清晰度。异常文件也存在 `errors.py` 与 `exceptions.py` 混用，影响跨包导航一致性。

### R9. Noqa、安全 SQL 与可观测性分布仍需补门禁

全库 `noqa` 主要集中在 data/platform，典型风险是 SQLite table name 拼接用 `# noqa: S608` 豁免。该模式可以有正当理由，但 10/10 需要白名单化 table identifier 或安全 table-name registry。深度报告还指出 `@traced` 分布很不均匀：data 很多，portfolio/risk/analysis/apps 等关键用户路径覆盖偏少。

## 8. 命名、抽象边界与领域划分专项审核

### 8.1 专项结论

本专项按用户要求采用严格口径：**只看正确性和合理性，不考虑改造成本、迁移成本和短期工作量**。判断标准是：如果目标是全球全市场量化系统的 10/10 架构，代码放置、领域切分、命名、port 归属和 composition root 是否都在概念上最正确。

结论是：**当前命名和领域划分已经明显优于旧架构，但从“做到最好”的标准看，仍存在一个缺失的 reference/market 能力边界，以及几处抽象归属偏差**。

专项评分：**7.4/10**。

| 子项 | 得分 | 判断 |
|---|---:|---|
| 命名一致性 | 7.8 | 后缀体系稳定，但 `Market`、`Service`、`Manager`、`TargetPortfolio`、`PositionReader`、`DatasetSpec` 等词在多上下文中仍不够唯一 |
| 抽象层级一致性 | 7.2 | import 边界强，但 application providers、DataProvider、Dataset routing 暴露了实现侧语言 |
| 领域划分正确性 | 7.3 | 12 包大方向正确；全球全市场理想模型下缺少独立 reference/market 能力边界 |
| 包/模块提炼充分性 | 7.0 | 需要提炼 reference domain、data catalog runtime、lineage、composition、OMS/reconciliation 等明确子域 |
| 可读性与维护性 | 7.5 | 文档和门禁强；data/application 高 fan-in、重复通用模块名和过宽 public API 仍影响长期可读性 |

一句话判断：**当前不是“依赖乱”，而是“概念还没有完全归位”**。机器门禁已经能守住禁止线；下一层要追求的是领域语言唯一、消费者 port 拥有、reference domain 独立、catalog/lineage/runtime 真实落地。

### 8.2 命名一致性审核

源码扫描显示，命名后缀已经形成体系：`Reader` 77 个、`Writer` 71 个、`Provider` 42 个、`Service` 32 个、`Protocol` 30 个、`Facade` 25 个、`Rule` 23 个、`Handler` 16 个、`Adapter` 15 个。`Manager` 只有 7 个，说明受限词没有大规模泛化。

深度报告进一步把 `Service` 做了职责归类：32 个生产 `*Service` 中，约 14 个更像 Store/Repository，占比约 44%。这说明问题不是后缀数量，而是后缀没有稳定表达架构层级。

较好的地方：

- `Reader/Writer` 在 Data storage 中基本表达物理读写职责。
- `Facade/Handler/Process/Builder` 在 application 层与 CQRS/R8 规则大体匹配。
- `Brokerage` 与 `BrokerGateway` 已通过文档和测试区分 runtime-facing 与 adapter-facing，不再是纯命名冲突。
- `apps` 非 registry 代码直接导入 capability 的情况只剩 `jobs/context.py` 的 Data Quality 窄豁免，边界语言基本一致。

仍需收敛的命名点：

| 命名点 | 当前问题 | 10/10 要求 |
|---|---|---|
| `Market` | `kernel.market`、`data.models.market`、`data.services.MarketService`、strategy `MarketState` 都叫 Market，但有的表示交易日历/宏观枚举，有的表示行情数据，有的表示市场状态 | 把 `MarketData`、`MarketReference`、`MarketState`、`VenueCalendar` 分清；`Market` 不再作为万能域名 |
| `Service` | 32 个 Service 中混有业务能力、查询能力、存储能力和生命周期能力；如 storage/sqlite 下的 `StrategyCatalogService` 更像 catalog store | 对持久化类统一用 `Store/Reader/Writer`；业务用例用 `Facade/Process/Handler`；稳定领域能力才用 `Service` |
| `Manager` | `BackfillManager`、`RetryManager`、`MetadataManager` 是流程协调语义，不完全是生命周期资源管理 | 若管理流程，优先 `Process/Coordinator`；若管理状态资源，保留 `Manager` |
| `TargetPortfolio` | strategy alpha、portfolio target_portfolios、execution target-like 语义相近但上下文不同 | 明确命名为 `StrategyTargetWeights`、`PortfolioTarget`、`ExecutionTargetView` 这类上下文限定名 |
| `PositionReader` | application port、portfolio positions、execution trade storage 都有同名概念 | 用限定前缀或包级 public API 文档区分：`ActualPositionReader`、`PortfolioPositionReader`、`ExecutionPositionReader` |
| `SignalRecord` | strategy signal record 与 execution signal record 表达不同生命周期阶段 | `StrategySignalRecord`、`ExecutionSignalRecord` 或用 canonical signal lifecycle glossary 约束 |
| `TradeRecord` | execution trade record 与 application 查询 DTO 同名 | DTO 层使用 `BacktestTradeView` / `TradeQueryResult`，领域层保留 `TradeRecord` |
| `DatasetSpec` | application config 中的 dataset scheduling spec 与未来 Data catalog spec 容易混淆 | application 保留 `IngestionTaskSpec`；data catalog 拥有 `DatasetSpec/DatasetCatalogEntry` |
| `Security`/`Instrument` | metadata reader 使用 `SecurityQuery`，kernel/data 多处使用 `Instrument`；全球市场里 security、instrument、contract、listing 不是同义词 | 建立 canonical glossary：`Instrument`、`Listing`、`TradableContract`、`SecurityMasterRecord` 各自只表达一个含义 |
| `errors.py` / `exceptions.py` | 多包混用错误文件名，apps 还同时存在两者 | 统一文件命名策略；若根类型叫 `DittoError`，推荐统一为 `exceptions.py` 并在包级文档声明 |

### 8.3 抽象边界审核

当前包级边界是优秀的：`strategy`、`portfolio`、`risk`、`execution`、`backtest`、`analysis` 的 import-linter 约束全部 kept，生产包不依赖 analysis，Platform 不再持有领域表名、通知模板和业务指标。

但抽象层级还有七处 10/10 差距：

1. **Application provider 仍像二级 composition root**
   `ditto_application.providers` 直接引用 `SQLiteClient`、`InstrumentReader`、`ComparisonWriter`、features storage runtime、execution trade storage 等具体实现。它是 DI wiring，不含业务逻辑，因此不是硬违规；但从 Clean/Hexagonal 的严格视角看，application 层知道太多物理实现。
   **10/10 要求**：具体 provider wiring 只能存在于 `apps.registry` 或独立 `composition` 包/层。`application` 核心只暴露 use case constructors、commands、queries、processes 和消费者 port。

2. **`DataProvider` 仍由 data 包定义，消费者语言不够纯**
   `ditto_data.provider.DataProvider` 因 Polars 约束留在 data 包，这比把 polars 放进 kernel 合理；但 backtest/application 消费它时仍接受了 data 包定义的上游世界观。
   **10/10 要求**：由 backtest/features/application 定义窄 port，例如 `HistoricalBarsPort`、`TradingCalendarPort`、`FeatureInputPort`；data 提供 adapter。若保留当前类型，应命名为 data-owned `DataQueryFacade`，不再伪装成跨平面 port。

3. **Dataset routing 抽象仍混杂“目录、调度、数据源、写入路由”**
   `Dataset` enum 在 data，`DatasetSpec/T1ConfigSpec` 在 application，fetch/write handler maps 也在 application。当前可运行，但抽象层级混着 data catalog、ingestion schedule、source adapter dispatch、storage write dispatch。
   **10/10 要求**：Data catalog 描述数据资产；application ingestion plan 描述任务调度；source/write routing 通过 registry/adapter table 注入，而不是散落 enum 分支。

4. **Reference/market domain 被夹在 kernel 与 data 之间**
   `kernel.instrument` 拥有 `AssetClass/Exchange`，`kernel.trading` 拥有 `InstrumentDefinition/InstrumentRules/MarketSnapshot`，data 又拥有 metadata/instrument/calendar/market service。全球全市场系统里，instrument master、listing、venue、calendar、session、trading rule、contract spec 是全平台共享的 reference domain，不只是数据获取的一部分。
   **10/10 要求**：提炼独立 `reference` 或 `market_reference` 能力边界。kernel 只保留极小稳定 ID/value object；data 只负责观察数据、来源、存储和 catalog；backtest/execution/risk/portfolio 通过 reference port 获取可交易对象、交易规则和日历。

5. **Kernel 有继续膨胀成共享杂物层的风险**
   kernel 目前仍小，但已经承载 trading、quality、research、publication_safety、strategy 等多域记录。它解决了跨包循环，但严格来说部分记录的语义所有者更像 features/strategy/analysis/data quality。
   **10/10 要求**：kernel 只保留跨全系统不可再分的语言：identity、clock/time、events、exceptions、primitive value objects、极少数基础 Protocol。领域 record 应回到 owning package，并通过消费者 port 或稳定 contract 暴露。

6. **Application 直接依赖 analysis service，而不是研究能力 port**
   application 当前直接 import `ResearchArtifactService`、`ResearchCatalogService` 和 analysis domain 类型。生产包不依赖 analysis 的合约仍成立，但 application 作为编排层直接使用 analysis 具体服务，会把研究存储/目录实现语言带入 use case。
   **10/10 要求**：application 定义 `ResearchCatalogPort`、`ResearchArtifactPort`、`ResearchDatasetPort`；analysis 提供 adapter。这样 analysis 仍可独立演进，application 只依赖用例需要的研究能力。

7. **Data source Fetcher Protocol 从 data 扩散到 ingestion use case**
   `MetadataFetcher/MarketFetcher/FundamentalFetcher/CapitalFetcher/MacroFetcher` 是 data source 侧语言，当前被 application ingestion process 使用。
   **10/10 要求**：application ingestion 定义 `IngestionSourcePort` 或按用例拆分的窄 port；data source adapters 实现这些 port，SourceRegistry 仍属于外层装配/adapter 生态。

### 8.4 领域划分正确性审核

当前 12 包比旧架构正确很多，但按 10/10 理想模型看，仍应补一个或明确提炼一个顶级/准顶级能力边界：**reference / market_reference**。它不是为了“多一个包”，而是因为全球全市场系统必须把“可交易对象及其市场规则”从“数据获取与存储”里分离出来。

理想领域重心应是：

| 概念 | 10/10 归属 | 当前主要落点 | 判断 |
|---|---|---|---|
| Instrument identity / listing / tradable contract | `reference` / `market_reference` | kernel + data metadata | 当前可用，但语义分散 |
| Venue / exchange / session / calendar | `reference` / `market_reference` | kernel.market + data metadata/calendar | 应从 data runtime 中抽出 canonical domain |
| Trading rules / lot size / tick size / fee schedule base | `reference` + execution/backtest reality model | kernel.trading + execution/backtest | 应有统一 rule source，backtest/live 共用 |
| Observed market data / bars / quotes / fundamentals / macro | `data` | data | 归属正确 |
| Dataset catalog / schema / PIT / lineage | `data.catalog` / `data.lineage` | data contracts + Dataset enum + application routing | 需要 runtime 化 |
| Ingestion plan / scheduling / retries / commands | `application.processes.ingestion` | application | 归属正确，但应避免拥有 Dataset 路由事实 |
| Strategy signal semantics | `strategy` | strategy + kernel.strategy | 基本正确，kernel 中策略记录需控制 |
| Derived/factor runtime | `features` | features | 基本正确，services 子域仍应细分 |
| Order intent / OMS / fills / reconciliation | `execution` | execution 薄骨架 + application process | 归属正确，成熟度不足 |
| Positions / holdings / accounting / portfolio target | `portfolio` | portfolio DTO/Protocol + backtest/accounting | 归属正确，runtime/store 不足 |

| 领域 | 当前划分 | 判断 | 是否需要提包/提模块 |
|---|---|---|---|
| `reference` / `market_reference` | 当前不存在 | 全球全市场理想模型缺口 | 应新增或至少从 kernel/data 明确提炼 |
| `data.catalog` | 只有 product-neutral contracts | 方向正确但未承担运行时目录职责 | 应补 catalog runtime/store/spec |
| `data.lineage` | 只有 contracts | 全球多市场、多源、多版本下必须有可追溯性 | 应补 lineage recorder/store/query |
| `data.providers` | 仅空 `__init__.py` | 空命名空间会误导架构读者 | 删除空目录或填入明确 data adapter facade |
| `application.runtime` | 仅空 `__init__.py` | 暂无实际语义 | 删除，或改为真实 runtime/composition 边界 |
| `portfolio.holdings/positions/target_portfolios` | 有 DTO/Protocol，缺少 runtime/store | 领域划分对，但还不是完整能力边界 | 应补 runtime/store/facade 和 public contract |
| `execution.orders/fills/reconciliation/gateways` | orders/fills/storage 有进展，gateway/reconciliation 薄 | execution 包边界正确，实盘/对账能力未产品化 | 应补 OMS/gateway/reconciliation 子模块 |
| `analysis.reports/diagnostics/experiments/screeners` | reserved namespace | 文档诚实，但保留空域会降低可读性 | 要么补最小 contract，要么以 maturity manifest 明确 reserved |
| `features.services` | derived catalog/query/artifact/gc 聚合较多 | 领域正确，但 `services` 过宽 | 应提 `features.derived_catalog`、`features.derived_runtime`、`features.publication` 子域 |

如果面向全球全市场 10/10，必须同时拥有两样东西：**reference domain** 和 **能力成熟度清单**。前者解决“概念该在哪里”；后者解决“哪些市场/资产/交易能力已经生产可用”。每个市场域、资产域、交易域应标注为 production / initial-focus / experimental / infrastructure / historical-compat，并被测试或架构检查引用。

### 8.5 边界泄漏审核

机器门禁已经挡住了硬泄漏：跨包 re-export 为 0，Platform 业务语义 smell 通过，apps 非 registry 能力直连受控，production-no-analysis kept。

剩余是软泄漏，主要体现为“概念在正确包之外被过早知道”：

1. application 知道 `Dataset` enum 和具体 source/write 路由。
2. application providers 知道具体 SQLite/storage 组件。
3. data 同时拥有 reference metadata、market data、source adapter、storage、catalog contract、quality/ingestion，导致它既像数据平台，又像市场主数据域。
4. application 直接依赖 analysis research services，而不是自身定义的 research port。
5. application ingestion 直接使用 data source Fetcher Protocol，说明部分 adapter 语言进入了用例编排层。
6. apps models/routes 暴露很多市场域模型，这对全球全市场方向不是错误，但应配合能力成熟度标注。
7. kernel 已承载 publication safety、research、quality、strategy 等跨域记录。当前还可接受，但 10/10 要求 kernel 保持“最小稳定语言”，新增共享类型必须证明至少两个核心平面长期需要。

这些软泄漏不会马上破坏架构，但会影响后续 agent 的默认放置判断。建议把它们转成 smell guard 或 architecture tests，而不是只写在文档里。

### 8.6 可读性与维护性审核

可读性优势：

- 包级 `CLAUDE.md`、`docs/architecture/boundaries-and-abstraction-standards.md` 和 import-linter 注释已经能解释大多数放置问题。
- 800 行文件红线有效，当前最大源码约 777 行。
- R8 CQRS、apps boundary、platform semantic ownership、cross-package re-export 都有机器保护。

维护性成本：

- `data` 仍是最大包，270 文件、约 31% 源码行数；新增数据集仍要跨 catalog/config/fetch/write/storage/quality 多处修改。
- `application` 是第二复杂包，尤其 ingestion coordinator、runtime builder、service factory、providers 高 fan-in。
- deep report 的 Top 大文件审计给出了更具体的拆分对象：`application/processes/ingestion/coordinator.py` 约 764 行且 33 个 import，`features/evaluation/evaluator.py` 约 746 行且 14 个类，`application/config.py` 约 614 行，`application/builders/runtime_builder.py` 约 626 行，`strategy/alpha/templates/stock_sector_rotation.py` 约 640 行且 12 个 stage/config 类。
- 通用模块名重复较多：`contracts.py` 12 个、`macro.py` 11 个、`errors.py` 10 个、`market.py` 9 个、`models.py` 8 个、`config.py` 7 个。包内合理，但跨包阅读时需要更强的 public API 指引。
- `helpers/utils` 数量不大，但 `application.processes.materialization.helpers` 这类名字过泛，若继续增长会掩盖领域语义。
- `__all__` surface 很宽，虽然不再跨包 re-export，但读者仍不容易判断哪些是稳定 API、哪些是内部实现。

### 8.7 面向 10/10 的欠缺清单

| 差距 | 当前状态 | 10/10 验收标准 |
|---|---|---|
| Reference domain | instrument/venue/calendar/rule 分散在 kernel 与 data | 有独立 `reference`/`market_reference` 能力边界，统一 instrument/listing/venue/session/calendar/trading rule |
| 目录治理 | DataCatalog 只有 contract，Dataset enum 仍主导运行时 | DataCatalog 有 runtime store、schema/source/calendar/asset metadata；新增数据集主要注册 catalog entry |
| 消费者 port | 少数 port 仍由 data/实现侧定义 | backtest/features/application 拥有窄 port，data/execution/platform 只做 adapter |
| Research port | application 直接 import analysis service | application 拥有 research use-case port，analysis 仅提供 adapter |
| 命名唯一性 | 同名 TargetPortfolio/PositionReader 在多上下文存在 | 关键领域词跨包有上下文限定名或 canonical glossary |
| Service 后缀 | 约 44% `*Service` 更像 Store/Repository | Store/Repository、Service、Coordinator/Process 后缀按职责互斥 |
| 异常命名 | `errors.py` / `exceptions.py` 混用 | 全库统一异常文件命名，并在包级 API 文档声明 |
| Composition root | application providers 引入具体 storage | apps registry 或专用 composition 层拥有全部具体实现 wiring；application 核心不 import SQLite/source/storage concrete |
| 子域成熟度 | portfolio/execution/analysis 部分子域是 DTO/Protocol/placeholder | 每个子域有 maturity 标注、最小实现或明确 reserved guard |
| 全球全市场路线图 | 多资产能力存在，但成熟度不一 | asset/venue/calendar/session/data-source maturity manifest 可被测试引用 |
| 可读性 | 大文件低于红线但高 fan-in 仍多 | coordinator/builder/provider 按单一用例或单一装配职责拆分 |
| 安全 SQL/noqa | table name 拼接依赖 `noqa: S608` 豁免 | table identifier 白名单或 table-name registry，豁免预算可测试 |
| 机器门禁 | import/smell 强，命名和成熟度主要靠文档 | 增加 suffix guard、Dataset enum usage budget、empty namespace guard、public API guard |

结论：**按不考虑成本的理想口径，当前确实缺一个 reference/market_reference 能力边界，也缺关键子域 runtime 化、命名消歧、消费者 port 回收、composition root 纯化和成熟度可执行化**。完成这些后，专项分可以从 7.4 提升到 9.0+；若再补齐全球市场数据目录、实盘/回测一致性、E2E/golden data 证明，以及命名/成熟度机器门禁，才接近 10/10。

### 8.8 最佳实践适配与过度设计复核

把后续建议放到 Clean/Hexagonal/模块化量化平台/DDD 边界借鉴/YAGNI/交易系统实践下复核，结论是：**方向成立，但必须用“最小可行抽象”落地，不能一次性复制成熟交易平台的全部复杂度**。

| 建议 | 业界依据 | 是否过度设计 | 修正后的落地边界 |
|---|---|---|---|
| `reference` / `market_reference` 能力边界 | 模块化量化平台需要统一 instrument/venue/calendar/trading rule；DDD Bounded Context 可作为边界语言参考 | **不过度**，因为这些概念已被 kernel/data/backtest/execution/risk/portfolio 共同使用 | 先做包内 context 或独立包的最小 contract：Instrument/Listings/Venue/Calendar/TradingRule；不先做完整 security master 产品 |
| DataCatalog runtime | Data platform/catalog 实践；Hexagonal 中应用不应靠 enum 路由外部资源 | **不过度**，因为 Dataset enum 已经导致多处 handler map 修改 | 先实现 runtime store + schema/source/schedule 映射；lineage 只记录最小 source/version/run，不做全血缘平台 |
| 消费者 port 回收 | Clean/Hexagonal 的依赖倒置：应用对外部数据/存储通过 port 交谈 | **不过度**，但不能为每个函数创建 port | 只对跨包、跨 runtime、或至少两个实现/测试 adapter 的对话建 port；纯内部函数不抽 |
| Composition root 纯化 | Hexagonal 外部 adapter 应在边界装配；application 保持 use case 编排 | **不过度**，当前 application providers 确实知道 SQLite/storage/source concrete | 下沉具体 wiring 到 apps registry 或 composition；避免引入复杂 DI 工厂层级，只保留薄装配模块 |
| Portfolio/Execution runtime 化 | Nautilus/LEAN 均把 portfolio/execution/OMS/reconciliation 作为核心 trading engine 能力 | **不过度**，但成熟度要分阶段 | 先补 paper/mock gateway、order state、reconciliation record；暂不做多 venue routing、L2/L3 order book、复杂 OMS mode |
| features services 拆子域 | 模块化要求同一模块名表达清晰职责；DDD 子域划分可借鉴 | **轻微风险**，如果只是移动文件会变成整理癖 | 只在 derived catalog/runtime/publication 出现独立生命周期和独立测试时拆；否则先用命名和 public API 收敛 |
| 命名词典和 suffix guard | 模块化系统需要稳定公共语言；DDD ubiquitous language 可借鉴 | **不过度**，成本低、收益高 | 先 guard `Service/Manager/Helper/Utils` 和跨包同名核心词；不要禁止所有自然语言变化 |
| maturity manifest | Thinnest Viable Platform 思路：用最薄平台减少认知负担 | **不过度**，尤其适合全球全市场但阶段能力不均的系统 | 先做 YAML/Markdown + 测试引用；不做复杂治理后台 |
| E2E/golden data | 测试金字塔和交易平台 replay/golden baseline 实践 | **不过度**，因为当前 25 skip 影响证明力 | 做最小 deterministic vertical slice；不要把 E2E 扩成慢速全市场验收 |
| 安全 SQL/noqa 预算 | 安全工程和架构门禁实践 | **不过度**，但应避免机械清零 | 对 S608/table name 做白名单机制；保留有原因、有预算、有测试的豁免 |

因此，当前建议不是“为了 DDD 而 DDD”，更不是追求传统 DDD 的战术模式。真正需要防止的是三类过度设计：

1. **把能力边界或借鉴来的 bounded context 等同于微服务或大拆包**：当前建议应先是代码边界、contract、门禁和最小 runtime，不是部署拆分。
2. **把未来全市场能力一次性产品化**：全球全市场是产品北极星，但近期只需要把 reference/catalog/maturity 的骨架做对，不需要完整多 venue OMS/order-book 引擎。
3. **为所有东西加 port**：port 应服务于跨边界替换、测试隔离和多 adapter，而不是成为每个类前面的仪式层。

按这个复核，边界治理类建议中 `reference`、DataCatalog、consumer port、composition root、E2E、maturity manifest 都是合适的，但它们不应再压过运行时地基。新的 P0 应是 runtime event/command/lifecycle、Backtest/Paper/Live 共享 seam、TimeContext、状态恢复和 continuous risk；reference、DataCatalog、consumer port、composition root、E2E、maturity manifest 更适合作为 P1 平台边界治理；features 拆分、命名统一、observability、安全 SQL 应按触发条件渐进落地，避免无行为收益的搬文件。

## 9. 运行时架构审计补充

`2026-05-08-runtime-architecture-critique-part1/part2.md` 的核心提醒是正确的：当前报告已经较好审计了 Python 包结构，但对“量化系统运行时如何实际运转”的审计不足。这个补充不推翻包结构结论，而是新增一条评分口径。

| 口径 | 当前判断 | 说明 |
|---|---:|---|
| Python 包结构与工程质量 | 8.6/10 | import-linter、smell guard、测试和类型约束很强 |
| 命名/边界/领域划分正确性 | 7.4/10 | reference、catalog、port、composition root 仍需归位 |
| 模块化量化运行时就绪度 | 6.4/10 | backtest runtime 较完整，但 live/paper、事件流、恢复、时间模型不足 |
| 全球全市场 live-ready 架构 | 5.0/10 | 当前没有完整实盘 loop、broker gateway adapter、流式数据和 crash recovery |

### 9.1 采纳的运行时批评

1. **EventBus 仍是轻量 stub**：源码中生产 `subscribe` 只有接口/实现定义，未见业务订阅方；publish 主要集中在 backtest steps。它现在是审计/扩展 seam，不是系统中枢。
2. **Backtest/Live 没有共享 runtime**：`EngineLoop`、`ProviderBackedDataFeed`、`BacktestBrokerage` 都是回测路径；`BrokerGateway` 只有协议和占位 gateway namespace；`LiveLoop` 尚未存在。
3. **状态恢复不足**：ingestion cursor、strategy run、execution position snapshots、feature checkpoints 等有持久化，但交易 runtime 的 account/order/risk state 缺少统一 journal、restore、rebuild 路径。
4. **时间模型分散**：PIT 能力存在于 `knowledge_date`、`effective_from/effective_to`、`as_of_date`、feature watermark、manifest 等局部机制中，但还没有统一 `TimeContext` 或 valid/transaction/knowledge time contract。
5. **数据路径偏批处理**：当前适合 A 股 ETF 日频研究/回测；若面向全球全市场 live，需要 streaming/incremental feed、paper/live adapters 和 replay/recording 能力。
6. **风控还不是持续运行时组件**：pre-trade/post-trade 规则存在，但 risk 尚未成为 submit/modify/fill 运行时路径的持续守门人。

### 9.2 需要修正的批评口径

1. **不能把 Databento/HFT 低延迟作为通用目标**：Ditto 是模块化量化系统，不是微秒级 ticker plant。WebSocket/Kafka/FPGA/lock-free queue 不应成为当前 P0。
2. **事件驱动不等于引入重型 message bus**：正确方向是先做确定性 in-process event/command model、生命周期和审计日志，而不是直接引入 Kafka/Redis 或 actor runtime。
3. **online feature store 不是当前 P0**：对日频 A 股 ETF 初期重点，batch feature catalog + PIT/golden replay 更重要；online serving 可列入 P2/P3。
4. **reference 能力边界不应被降到很后**：runtime 地基优先，但 instrument/venue/calendar/trading rule 是 backtest/live/risk/execution 共享语言，应与时间模型和 DataCatalog 并行演进。

### 9.3 运行时 10/10 的真实差距

| 差距 | 当前状态 | 10/10 最小验收 |
|---|---|---|
| 运行时通信模型 | EventBus 有接口但无订阅业务流 | 有最小 `RuntimeEvent` / `RuntimeCommand` / `RuntimeLifecycle`，关键路径可订阅、可审计、可 replay |
| Backtest/Paper/Live 共享路径 | 只有 backtest loop | 至少共享 order planning、risk gate、brokerage abstraction、state transition、event journal |
| 状态恢复 | 部分存储有 snapshots/checkpoints，交易 runtime 无统一恢复 | account/order/fill/risk state 可从 persisted records 或 event journal rebuild |
| 时间模型 | `Clock` + 分散 PIT/as_of/knowledge_date | 统一 `TimeContext`，明确 trade time、knowledge time、effective time、processing time 的边界 |
| 流式/增量数据 | HTTP/file batch + full-load DataFeed | 最小 incremental feed interface + replay recording；不要求 HFT 延迟 |
| Continuous risk | pre/post 装饰式规则 | risk gate 嵌入 order submit/modify/fill path，支持状态化风险恢复 |
| Runtime observability | trace 分布不均 | runtime path 有 trace/span/metric/error mapping/journal id |

## 10. 面向 10/10 的理想架构建议

本节只按架构正确性排序，不考虑改造成本；实际落地应遵守 8.8 的“最小可行抽象”护栏，先补运行时地基，再推进边界和子域 runtime 化。

### P0：必须补齐的量化运行时地基

1. **定义最小 runtime event/command/lifecycle 模型**
   - 保留轻量 in-process 设计，不引入重型消息中间件。
   - 最小对象：`RuntimeEvent`、`RuntimeCommand`、`RuntimeStateTransition`、`RuntimeLifecycle`。
   - 验收标准：order submit/fill、risk decision、data slice ready、strategy decision 至少有可订阅、可记录、可 replay 的事件。

2. **建立 Backtest/Paper/Live 共享 runtime seam**
   - 抽出 shared runtime contract，而不是让 live 复制 `EngineLoop`。
   - 先实现 paper/mock gateway，不急于真实券商。
   - shared seam 必须包含 **OMS Lite contract**：`ClientOrderId`、可选 `BrokerOrderId` 映射、`OrderIntent -> Order -> OrderTicket -> FillEvent -> Position` 状态流、order journal、幂等 submit/cancel/modify、broker event reconciliation skeleton。
   - 验收标准：同一 strategy/risk/planner/brokerage port 可跑 backtest 和 paper runtime。

3. **统一时间模型和 PIT 上下文**
   - 定义 `TimeContext`：trade time、knowledge time、effective time、processing time。
   - backtest manifest、data catalog、feature materialization、execution/risk 都引用同一时间语义。
   - 验收标准：新增 PIT 数据或特征时必须声明 time semantics。

4. **补状态恢复和幂等运行时记录**
   - account/order/fill/risk runtime state 可从 records 或 event journal rebuild。
   - 先覆盖 paper/backtest，不要求完整 live HA。
   - 验收标准：中断后能从最后 durable checkpoint 或 event journal 恢复运行状态。

5. **把 risk 放入运行时路径**
   - risk gate 不只是 pre/post batch scan，而是 order submit/modify/fill 的必经步骤。
   - 验收标准：风险拒绝、resize、lock、unlock 都产生审计事件，并可重放验证。

### P1：必须补齐的量化平台边界

6. **提炼 `reference` / `market_reference` 能力边界**
   - 拥有 instrument master、listing、tradable contract、venue/exchange、calendar/session、trading rule、lot/tick/settlement rule。
   - kernel 只保留 `InstrumentId` 等极小稳定标识；data 不再拥有 canonical market reference 语义，只提供数据与 adapter。
   - 起步形态应是最小 module/package + Protocol + DTO + adapter seam，不是完整 security master 平台或微服务。
   - 验收标准：backtest/execution/risk/portfolio 获取交易规则和日历时依赖 reference port，而不是 data service 或 kernel 大对象。

7. **把 DataCatalog 从 contract 推进到 runtime catalog**
   - 增加 SQLite/Parquet-backed catalog implementation。
   - 把 Dataset 的 asset_class、date_schedule、source/schema 映射迁入 catalog/spec。
   - 验收标准：application 中直接 `Dataset` 使用文件数从 12 降到 3 以下；新增数据集不再修改多个 handler map。

8. **让消费者拥有 port，provider 只做 adapter**
   - 把当前 data-owned `DataProvider` 演进为消费者视角的 `DataPortal` port，但 port 不应归 data 拥有。
   - backtest 拥有 `HistoricalBarsPort`、`InstrumentRulesPort`、`TradingCalendarPort`。
   - runtime/backtest 视角的 `DataPortal` 最小能力包括 history、slice/latest、calendar、factor；spot value、adjustments、subscribe 可先保留为显式后续扩展点。
   - features 拥有 `FeatureInputPort` / `DerivedArtifactPort`。
   - application 拥有 use case 所需的窄 orchestration port，包括 `ResearchCatalogPort`、`ResearchArtifactPort`、`IngestionSourcePort`。
   - data、reference、execution、platform 提供 adapters，不向内层输出自己的大 facade 作为通用 port。
   - 只为跨边界、多实现、或需要 in-memory/golden adapter 的对话建 port；单实现内部函数不加仪式层。

9. **净化 composition root**
   - `application` 核心不再 import `SQLiteClient`、具体 Reader/Writer、source adapter、runtime storage concrete。
   - `apps.registry` 或独立 `composition` 层拥有全部具体 wiring。
   - `application.providers` 若保留，只能是 Protocol-oriented factories，不直接触碰物理实现。

10. **补齐稳定 E2E/golden data 闭环**
   - 提供最小可提交样本数据或生成器，消除当前 25 个 TDX 样本 skip。
   - 覆盖至少：metadata ingest、ETF daily ingest、DQ、factor materialization、strategy run、backtest、paper execution intent/fill、report export。
   - 验收标准：fast gate 中 E2E 不因本地样本缺失而跳过关键路径。

11. **明确全球全市场路线图下的能力成熟度分层**
   - 将资产域和市场域标注为：生产可用、初期重点、实验中、基础设施预留、历史兼容。
   - 在 `CLAUDE.md`、data/strategy/backtest 包文档中明确“全球全市场北极星”和“A 股 ETF 初期能力重点”的关系。
   - 验收标准：maturity manifest 可被测试读取，避免 reserved namespace 被误认为 production-ready。

### P2：必须归位的子域和门禁

12. **拆分高 fan-in orchestration 文件**
   - 优先：`application/processes/ingestion/coordinator.py`、`application/builders/runtime_builder.py`、`application/providers.py`。
   - 目标不是追求小文件，而是让每个文件只表达一个用例或一个装配职责。

13. **把 Portfolio/Execution 占位协议推进到最小实现**
   - holdings/positions/target_portfolios 增加 store 或 application facade。
   - execution gateways 至少提供 paper/mock gateway，reconciliation 增加最小记录模型。
   - 以 **OMS Lite** 命名下一阶段 execution 目标：order identity、order state machine、partial fill contract、order/fill journal、幂等撤改单、broker event reconciliation 应成为 execution 的一等子域，不只通过 backtest 或 application process 间接表达。

14. **把 features services 拆成领域子域**
   - `features.services` 现在承载 derived catalog/query/artifact/gc/publication 相关能力。
   - 理想结构应显式区分 `features.derived_catalog`、`features.derived_runtime`、`features.publication`、`features.artifacts`。

15. **收敛 public API、命名和异常入口**
   - 每包定义 public surface 文档。
   - `Service/Store/Repository/Coordinator/Process` 后缀按职责互斥。
   - `SignalRecord/TradeRecord/PositionReader/TargetPortfolio` 等跨包同名词进入 canonical glossary。
   - 统一 `errors.py` / `exceptions.py` 策略，避免同一工程两套异常入口。

16. **补机器门禁**
   - suffix guard、Dataset enum usage budget、empty namespace guard、public API guard、maturity guard。
   - Writer 查询式辅助方法加规则：8 个 `get_checksum` 要么定义为 idempotency 例外，要么迁到 Reader/checksum service。
   - 安全 SQL/noqa 预算：table name 改为白名单 identifier 或 table-name registry。

17. **系统化 observability 和复杂度扫描**
   - runtime path 有 trace/span/metric/error mapping/event id。
   - 增加 complexity/dead-code/security 扫描，补足 ruff/type/test/import-linter 之外的质量门禁。

18. **研究/回测/实盘一致性路线图**
   - 对标 LEAN/NautilusTrader，把时间模型、订单语义、费用/滑点、数据快照版本、回放方式写成可验证 contract。
   - online feature serving、低延迟 streaming、真实 broker adapter 进入后续阶段，不作为当前 P0。

## 11. 结论

当前架构已经从“文档上有边界、源码里仍有旧平面惯性”的状态，进入了“边界清楚、机器可守、能力包基本自治”的状态。按包结构和工程综合质量看，Ditto 现在是优秀水平，8.6/10 成立。

但如果只按 10/10 理想架构的正确性和合理性看，专项分应更严格：**7.4/10**。如果再把运行时架构单独拿出来看，当前模块化量化运行时就绪度约 **6.4/10**，全球全市场 live-ready 架构约 **5.0/10**。还不能给高分的原因也很明确：EventBus 没有形成业务订阅流，backtest/paper/live 没有共享 runtime，BrokerGateway 没有实现，交易状态恢复不足，统一时间模型缺位；同时 reference/market_reference 能力边界、DataCatalog runtime、DataProvider/data Fetcher/analysis research port、composition root、E2E/golden data、OMS/reconciliation 仍未闭环。

面向“做到最好”，目标应从“保持 12 包干净”升级为两层任务：第一层是**运行时地基**，包括 runtime event/command/lifecycle、Backtest/Paper/Live 共享 seam、OMS Lite、统一时间模型、状态恢复、continuous risk；第二层是**能力边界治理**，包括 reference domain 独立、DataPortal/DataCatalog 运行时化、消费者 port 拥有、composition root 纯化、端到端证明、能力成熟度可执行化、命名词典机器化。两层都完成后，Ditto 才能从组织良好的研究/回测框架，进化为架构正确的全球全市场模块化量化系统。

## 12. 本次验证命令

```bash
pixi run -e dev arch-check
# Contracts: 36 kept, 0 broken
# Architecture smell check passed

pixi run -e dev check
# ruff check passed
# ruff format: 1506 files left unchanged
# basedpyright: 0 errors, 0 warnings, 0 notes
# fast tests: 6273 passed, 25 skipped
# import-linter: 36 kept, 0 broken
# architecture smell check passed
```
