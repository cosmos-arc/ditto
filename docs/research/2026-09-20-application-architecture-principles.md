# Application 层架构原则复核

日期：2026-09-20。性质：一手资料调研与 Ditto 适用性建议；包含代表性源码调用链复核，不代表全仓语义审计通过，也不直接授权重构。用户目标是架构合理、职责内聚、分层清晰，不以 application 行数减半或占比下降验收。

## 结论

保留现有模块化单体和 `apps → application → 能力包` 主线，Agent 仍经 application 使用业务能力。application 应形成明确、可测试的用户用例边界，承担跨能力协调、任务进度、恢复与结果组合；金融计算和各能力的不变量由所属能力包负责，物理依赖由外层装配。优雅的标准是一次规则变化能找到唯一归属、调用者不需要了解内部步骤、失败后能够恢复，而非层数、文件数或代码量。

这与仓库已有[边界标准](../architecture/boundaries-and-abstraction-standards.md)及[架构入口](../architecture/agent-context-pack.md)总体一致。下面的规范映射是本次建议；具体搬移对象仍须用源码调用链证明，不应凭目录大小预判。

## 一手资料实际支持什么

| 来源 | 原始观点 | 对 Ditto 的意义及适用边界 |
|---|---|---|
| [Randy Stafford：Service Layer，收录于 Fowler 的企业应用架构模式](https://martinfowler.com/eaaCatalog/serviceLayer.html) | 服务层表达应用可用操作，协调响应与事务，避免不同入口重复交互逻辑。 | Web、CLI、Agent 共享同一用例语义。并未要求服务层只剩一行转发；也不能据此把所有领域算法集中到 application。 |
| [Microsoft 官方 DDD 分层说明](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/ddd-oriented-microservice) | application 协调用例，可保存任务进度；业务状态与规则由领域层拥有。逻辑分层不等于部署划分。 | “薄”首先是职责薄，不是全仓代码比例低。借用其分层解释，不照搬 .NET 项目布局、微服务或聚合类模板。该页引用 Evans，不是 Evans 原书的在线全文。 |
| [Robert C. Martin：The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) | Use Cases 包含应用特定规则，协调实体；依赖朝内，框架、数据库及传输细节在外侧。图中的圈数不是固定要求。 | 与 DDD “不放业务规则”的措辞需按语义区分：用例步骤和授权检查编排可在 application，费用算法、估值、信号及研究统计不能被各用例复制。 |
| [Alistair Cockburn：Hexagonal Architecture 原文](https://alistair.cockburn.us/hexagonal-architecture) | 核心应可由 UI、自动测试或程序驱动；端口描述有意义的交互，适配器处理外界技术差异。 | FastAPI、AG-UI、SDK、MCP 均不能成为金融事实或准入政策的唯一实现。端口数量取决于真实交互，不要求六个端口或每个函数一套 interface。 |
| [John Ousterhout：Modular Design 课程讲义](https://web.stanford.edu/~ouster/cgi-bin/cs190-winter18/lecture.php?topic=modularDesign) | 接口包括签名、行为、副作用和使用约束；好的模块用较简单接口隐藏更多实现知识。 | 深度是封装收益，不是调用栈深度。只改名称、原参数透传且不增加边界保障的层，应审查是否合并；安全边界不能仅因短小而删除。 |
| [Martin Fowler：Monolith First](https://martinfowler.com/bliki/MonolithFirst.html) | 服务拆分有额外运维成本，稳定边界难以预先确定；单体仍需关注模块化。作者明确承认该经验依据有限。 | 个人本地工作台没有因代码量大就拆网络服务的理由。独立部署应由隔离、资源或运行要求证明，而不是把能力包机械映射为微服务。 |
| [Martin Fowler：CQRS](https://martinfowler.com/bliki/CQRS.html) | 读写模型分离在部分场景有用，也可能引入风险与复杂度；模型可以共享数据库。 | `commands/queries` 命名不要求双数据库、消息总线或全系统事件溯源。保留实际账本审计保障，不扩展为所有对象的统一事件平台。 |

## 职责判断：先看“为什么变化”，再看放在哪里

以下为依据上述原则和仓库边界得出的建议，不是外部资料对 Ditto 源码的结论。

| 判断对象 | 推荐归属 | 审查问题 |
|---|---|---|
| 一次选股、回测、组合比较或研究晋级用例的调用顺序、前置条件与结果组合 | `application` 的对应领域用例 | 是否不依赖 HTTP/Agent 入口也能完整执行和测试？ |
| 跨步骤任务进度、幂等协调、失败恢复、取消与提交点 | 用例所有者；物理持久化经现有端口/适配器 | 删除这段编排是否会改变重试、重复写入或恢复保证？ |
| PIT 可见性、费用、估值、风险、因子/研究统计等可独立表达的领域规则 | `data`、`execution`、`portfolio`、`risk`、`features`、`backtest` 或 `analysis` 的实际语义所有者 | 同一输入通过不同入口是否得到同一判断？能否脱离用例编排验证？不要为迁出 application 随意塞进 kernel。 |
| 多来源证据收集与无副作用的页面查询结果组合 | `application.queries`；领域计算调用能力包 | 是否把“查询拼装”变成了第二套收益/估值/准入算法？ |
| HTTP DTO、AG-UI 事件转换、OpenAPI、前端展示模型 | 传输适配与 Web feature adapter | 更换流式协议是否迫使金融规则改变？ |
| SDK、模型/存储/网络客户端、配置与物理依赖连接 | 现有技术适配器与 `apps/backend` composition root | application 是否自行查环境变量、实例化物理客户端或依赖 SDK 类型？ |

审批也要区分归属：业务动作是否满足领域准入由规则所有者判断；用例协调何时检查与执行；Agent 运行时管理模型动作审批与预算。三者可协作，但不能在三个入口复制同一政策，不能用用户对话替代可信权限。

application 可以同时拥有许多清晰的小用例，因此总体不小；单一用例如果拥有多套领域算法、存储布局和传输事件知识，则即使行数很少也不合格。建议先在现有 commands/queries/processes 内按业务对象形成可导航的聚合，不因套用“垂直切片”再平行建一套目录和 handler 框架。

## 把“优雅”变成可验证的验收

不用综合评分或任意阈值。每个候选改造选一个真实场景，提交以下证据即可：

1. **归属清楚**：列出入口 → 用例 → 规则所有者 → 外部适配器的调用链，以及唯一不变量实现。跨包关系不仅通过 import 检查，还能解释语义归属。
2. **变化局部**：以“增加一种费用规则”“更新源字段映射”“替换 AG-UI 流事件转换”等具体变化为例，说明应该变动哪些模块；不应迫使无关领域修改。
3. **接口有效封装**：调用者只需给出用例必要信息，不用手工拼内部存储路径、阶段序列或重复校验。可在边界完成一个操作，结果明确成功、失败及证据身份。
4. **测试能隔离原因**：领域算法用确定性输入验证；用例验证协调与恢复；适配器验证真实契约。避免用大量内部 mock 断言调用顺序来替代业务结果验证。
5. **保障不退化**：PIT、源快照、账本一致性、审批、预算和恢复行为保持；迁移前后的关键输入输出与副作用相符。对有意改变的语义单独列出决策及验收。

LOC、模块数、依赖数量可以作为排查线索与结果记录，不能单独作为接受或拒绝重构的标准。两个设计都满足保障时，优先选择让调用者掌握更少知识、真实变更触及更少无关模块的一种；不为统一外观而增加 DTO、Protocol、factory 或泛型执行框架。

## 对实施计划的建议

将 application 票改为“架构职责与边界校准”，先完成代表性调用链审计，再按问题拆出最小修正。每项列明保留、合并或迁移的理由，不能只列待移动文件。领域归属本已清晰的部分应保留；需要改动边界的部分给出具体前后依赖图和消费者证据。安全恢复复杂度不作为可删冗余。

优先检查已有复审指出的组合比较/研究统计、命令幂等和流程恢复路径，但这些是调查入口，不是已判定必须迁移的清单。无需先创建通用架构平台、独立服务、全局 CQRS 双栈，或给每个叶函数加接口；只有真实技术边界、替换需求或测试隔离需要时才引入相应机制。

## Ditto 代表性调用链复核

基线：`4694f68c3a91bb0642d7204741e1924195088fac`。以下为实际源码核查，不是行业资料对本仓库的判断；覆盖有代表性的正反案例，并非逐一审完全部 application 模块。

| 调用链与证据 | 结论 | 建议 |
| --- | --- | --- |
| [research job](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/apps/backend/src/ditto_apps/jobs/flows/research.py#L39) → [ResearchDatasetFacade.build](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/queries/research.py#L102) → 写 Parquet/JSON 和 catalog 快照；同一 facade 的 export 直接写 CSV/SQLite | **优先校准职责**。`queries` 内存在真实副作用；并非仅文件命名不美观。`_export_sqlite` 还知道连接、SQL 和落地格式。 | 构建/导出作为 application process/command，用现有能力的 artifact/storage adapter 承担物理写入；读取报告保留只读 query。先列消费者、写入/恢复语义及事务边界，再改归属，不能只搬文件。 |
| [_comparison_evidence._return_metrics](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/processes/experiments/_comparison_evidence.py#L644) 与 [backtest.statistics_returns](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/backtest/src/ditto_backtest/statistics_returns.py#L43) | **计算与编排需分清，暂不能直接去重**。application 计算收益、Sharpe、Calmar、回撤；两处起点和不可计算语义不同。 | 研究 fold 指标优先由 analysis 的研究规则拥有，application 留证据取得、验证及结果组合；backtest 保留回测报告口径。先定义差异，再判断真正相同的计算能否复用；不得违反 analysis/生产能力隔离，也不为复用随意增加 kernel 或 shared 包。 |
| portfolio HTTP → [GetPortfolioComparisonQuery](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/queries/portfolio_comparison.py#L148) → portfolio.normalize/compare | **合理，保留**。应用层核对三腿身份和快照，能力包负责归一化/偏差计算，HTTP 无需知道内部账本加载步骤。 | 后续历史收益扩展沿用这一分工；不因多一个 source port/query port 或验证代码较多就删层。 |
| selection facade → [RunIndustryAndSecuritySelection.execute](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/processes/selection/run_industry_and_security_selection.py#L58) → strategy 服务及持久化端口 | **合理，保留**。封装输入转换、错误转换、跨阶段时间身份绑定和结果保存。 | facade 与 process 不是原参数简单透传，不能按类数裁掉。保存多工件的失败一致性需在对应交付中验证，本轮未宣称其事务原子性。 |
| coordinator → [ExperimentRecoveryOrchestrator](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/processes/experiments/_coordinator_recovery.py#L58) → [scheduler store](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/processes/experiments/scheduler_store.py#L306) → analysis reader/writer | **有真实职责，保留恢复保证**。取消、租约、重试谱系、快照聚合不是无意义碎片。 | 可按状态转换内聚性审查内部组织，但不能合成一个巨型 coordinator 或把恢复职责删掉以减少行数。store 有部分转发，也封装 fence 与组合快照；应按方法职责评估，不整类删除。 |
| [commands.mutation_idempotency](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/commands/mutation_idempotency.py#L1) → application.mutation_idempotency | **核查可删除转发的候选**。模块只重导出；当前静态直接消费者只见对应测试。 | 继续核实动态消费者和公共兼容，确认后让消费者从定义模块导入；只清理转发，不删除实际幂等保证。 |
| [AppSelectionProvider](https://github.com/cosmos-arc/ditto/blob/4694f68c3a91bb0642d7204741e1924195088fac/packages/application/src/ditto_application/providers_selection.py#L35) 注入已有服务/端口并构造用例；apps registry 组装物理环境 | **不能一概迁走 DI**。这部分为应用对象组合，非自行创建外部网络/数据库连接。 | 区分“用例组合”与“物理配置/资源生命周期”；保持 apps/backend 为 composition root，不为了目录纯度机械搬迁全部 provider。 |

### 两个防止误判的具体例子

- 初始资金 100，第一条 NAV 为 90，最后 NAV 为 99：fold 证据从初始资金计算得到 -1%；`total_return([90, 99])` 得到 +10%。这说明输入起点合同不同，不是本轮已经证明某个公式错误；不经语义校准直接合并会改变结果。前者还将零波动标为不可计算，后者部分辅助函数返回 0，两者不可无条件替换。
- `commands/strategy.py` 的 sqlite3 与 `post_ingest.py` 的 httpx 导入主要用于捕获异常；这暴露了技术错误类型耦合，可在对应适配器修订时归一，但不能只因 import 就声称 application 自建数据库/网络客户端。`queries/research.py` 则有实际 connect/CREATE/INSERT/write 行为，证据级别不同。

### 验证与实际边界

本轮 `task arch-check` 成功：分析 1,649 文件、6,562 依赖，44 条合同 kept、0 broken，architecture smell check 通过。有一项既存 unmatched-ignore 警告指向已不存在的 `ditto_agent.sandbox.**`；已列入死契约核查范围，不在本轮修改规则。

通过检查不能证明 query 无副作用：现有 R8 主要约束跨命名空间导入，对同文件直接写入及从能力服务调用写入不构成完整语义证明。后续应以真实用例的无写入行为检查和代码审查补齐，不靠堆叠名字正则或为了保持绿色放宽规则。

本轮未运行数据构建、SQL 导出、回测、模型或真实账户，不把源码复核称为持续运行验收。

## 推荐修订后的执行方式（维护者已于 2026-09-20 确认）

[最终决定](https://github.com/cosmos-arc/ditto/issues/248)确认以下顺序与验收原则；具体切片仍须列出调用链、消费者和验证，不构成已实施。

1. 保持模块化单体及清晰能力包；将 application 票改名为“职责、内聚与分层校准”，撤销减半目标。
2. 第一批聚焦研究数据集 facade 的读写/物理 I/O 归属；第二批校准研究统计与回测统计的语义及所有者。两批都先给前后调用链、消费者、错误/副作用合同与验证，再实施。
3. 恢复、PIT 身份、幂等和审批不作删减指标；只在具体状态机更内聚、调用者知识更少且保证不变时调整。
4. 不全仓重排目录、不创建泛型 handler 框架、不预先给所有函数加 port。行数增减仅记录结果，接受标准是规则归属唯一、行为与命名一致、变化局部、调用接口清晰、恢复可验证。
