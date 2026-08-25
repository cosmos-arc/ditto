# Ditto 统一产品路线图与执行计划

> 日期：2026-08-25<br>
> 状态：当前跨仓库执行事实源<br>
> 产品边界：A 股 ETF、本机单操作者、日频人工决策、研究与交易工作台<br>
> 后端基线：`ditto/main@69967f97`<br>
> R5 实现基线：`ditto/codex/r5-governed-agent@a971a253`<br>
> 前端基线：`ditto-app/codex/r1-r5-frontend-completion@a54122a`<br>
> 前端专项计划：[Ditto 前端产品体验恢复计划](https://github.com/cosmos-arc/ditto-app/blob/main/docs/plans/2026-08-25-frontend-product-experience-recovery-plan.md)

## 1. 执行裁决

这是一份完整产品路线图，不是单独的前端改版计划。

当前 Ditto 的主要矛盾已经从“量化能力是否存在”变成“能力是否以一致、可信、可持续使用的产品工作流交付”。后端 R1—R4/G3 已经形成较强的日频量化底座；R5 的 38 个实现任务和 release preflight 已在独立分支完成，但尚未进入 `main`。前端具有成熟原型、信息架构和工程底座，却没有把这些能力稳定地呈现为 live 产品。

因此，下一阶段不继续横向扩充新能力，也不直接启动 R6 分钟级或 R7 全球化。优先把已完成的 R1—R5 收敛为一个真正可用的个人量化工作站：

1. 合并并冻结真实能力与 API 基线。
2. 恢复统一 Shell、视觉语言和 mock/live 单一呈现树。
3. 先完成日常决策与交易闭环，再完成研究、Agent、市场与数据闭环。
4. 以跨仓库用户验收作为完成定义，不再用“后端测试通过”或“页面路由存在”代替产品完成。
5. 当前版本不建设复杂权限、安全隔离、多租户或机构平台能力。

## 2. 文档职责

| 文档 | 当前职责 |
|---|---|
| 本文 | 当前产品范围、跨仓库架构、执行顺序、里程碑和验收事实源 |
| [长期能力路线图](../roadmaps/ditto-development-roadmap.md) | R0—R7 长期能力地图；不再直接决定当前执行优先级 |
| [2026-08-04 状态评估](../reviews/2026-08-04-roadmap-status.md) | 历史审计快照；不得用于判断当前 R4/R5 状态 |
| [R5 权威设计](2026-08-12-r5-governed-quant-research-agent-design.md) | R5 领域、PIT、Agent 运行时和发布边界 |
| [R5 实施计划](2026-08-12-r5-governed-quant-research-agent-implementation-plan.md) | R5 分支内 38 个任务及验收证据 |
| [前端体验恢复计划](https://github.com/cosmos-arc/ditto-app/blob/main/docs/plans/2026-08-25-frontend-product-experience-recovery-plan.md) | 页面、Shell、视觉、交互和前端工程施工图 |

冲突时仍以机器约束、当前源码/测试、架构文档、本文、专项计划的顺序判定。本文不覆盖 PIT、风险、执行或 Agent 的既有安全语义。

## 3. 当前产品与架构完成度

### 3.1 已经具备

- R1：本机日频人工交易、信号、订单、成交、账户和 EOD 恢复闭环，G1 已通过。
- R2：A 股日频数据产品、PIT、质量、血缘和 live evidence。
- R3：因子、实验、回测、策略审查、发布、重新激活和研究治理，G2 已通过。
- R4：组合优化、连续风险、压力测试、归因、账本和 Daily Decision V3，G3 已通过。
- R5 分支：Evidence/Author Copilot、受控研究 Campaign、shadow Decision Briefing、评测、恢复和发布预检，38/38 任务完成。
- 前端：五域 IA、28 个高完成度原型、设计 token、路由、typed API/hooks 和完整工程门禁底座。

### 3.2 尚未形成产品完成

| 维度 | 当前判断 | 核心缺口 |
|---|---:|---|
| 产品定位与工作流 | 80%–90% | 原型和领域清楚，但 Release 与用户闭环尚未统一 |
| 后端日频核心能力 | 85%–90% | R1—R4 已完成；仍需按前端工作流核对 display DTO 和 API |
| R5 Agent 能力 | 分支实现 100%，主线集成 0% | 尚未合并；默认 flags 关闭；前端控制台未按产品规格交付 |
| 前后端契约与 live 接线 | 60%–70% | 页面会直接拼接底层响应；部分 live 页面占位或降级 |
| React 视觉与交互 | 30%–40% | Shell 和主工作面偏离原型；79 个 overlay 仍是 prototype-only |
| live 用户工作流 | 40%–50% | Trading/Research 深浅不一，Home/Markets/Platform live 不完整 |
| 个人 Beta 发布就绪 | 40%–50% | 缺跨仓库 E2E、视觉硬门、恢复演练和真实日常使用验收 |

综合判断：后端工程成熟度较高，但完整可用产品约为 **50%–60%**。这个比例按用户能否完成端到端工作计算，不是两个仓库代码量的平均值。

### 3.3 最重要的欠缺

1. **路线图口径漂移**：旧状态文档与 R5 实际分支状态不一致，前后端又各自声明完成。
2. **缺少跨仓库完成定义**：后端 release、API、React 页面和原型验收没有绑定在同一个 Gate。
3. **前端呈现架构分裂**：mock/live 使用不同 UI，造成 live 能力越多，产品视觉越偏离。
4. **能力没有转译成用户任务**：后端返回领域对象，前端缺少稳定的 PageModel/display DTO 层。
5. **视觉门禁假绿**：当前审计能发现几何漂移，却不会因超阈值失败。
6. **R5 未收口到主产品**：代码已完成，但合并、默认配置、页面集成和用户价值验收尚未完成。
7. **扩张冲动早于产品闭环**：分钟级、全球资产、机构化都不应抢占当前工作站收口资源。

## 4. 目标产品

### 4.1 核心用户与价值

核心用户是一个同时承担研究、组合、风控、交易和运维职责的个人量化交易者。产品每天应回答四个问题：

1. 市场和数据发生了什么？
2. 哪些研究证据值得转成策略或观察项？
3. 今天应该做什么，为什么，风险在哪里？
4. 实际执行和预期有什么偏差，下一步如何修正？

主工作流固定为：

```text
Observe → Discover → Research → Validate → Decide → Execute → Review
```

AI 是证据解释、草案生成和受控研究的辅助层，不是独立聊天产品，也不成为事实源、回测裁判或自动交易者。

### 4.2 当前产品边界

- A 股 ETF 优先，日频优先。
- 本机或个人私有环境，单操作者。
- 人工审批策略变更和交易建议。
- 使用既有数据、研究、组合、风险、执行和 Agent 能力。
- 产品首先满足持续日常使用，不以对外商业化、机构部署或功能数量为目标。

## 5. 统一系统架构

### 5.1 跨仓库数据流

```text
ditto-app PageView
  ← PageModel mapper
  ← TanStack Query / command hooks
  ← apps HTTP DTO / SSE
  ← application query/command orchestration
  ← data | features | strategy | backtest | analysis
     portfolio | risk | execution | agent
  ← provider/store adapters
```

边界裁决：

- `ditto-app` 只消费 `apps` 暴露的稳定 DTO，不理解后端 store、provider 或包内部模型。
- `apps` 仍是唯一 composition root 和 HTTP/CLI 适配层，不承载领域决策。
- `application` 编排跨能力用例；不把页面拼装逻辑下沉到领域包。
- 领域能力继续由其源包拥有；不为前端方便增加跨包 re-export 或聚合型“万能服务”。
- R5 合并后保持 `apps -> agent -> application`，Agent 不直接访问 capability，也不成为新的全局编排中心。
- mock/live 只切换数据 adapter，必须进入相同 PageModel 和相同 PageView。

### 5.2 能力平面、提供者与消费者

| 用户闭环 | 后端提供者 | 编排/跨界合同 | 前端消费者 |
|---|---|---|---|
| 市场与数据观察 | `data`、`features` | `application` 查询；`apps` display DTO | Home、Markets、Data Products |
| 因子到策略研究 | `features`、`strategy`、`backtest`、`analysis` | 研究 facade、experiment/review commands | Research、Alpha、Experiments、Review |
| 日常决策与调仓 | `portfolio`、`risk`、`application` | Daily Decision V3、风险/组合 projection | Trading Overview、Signals、Portfolio、Risk |
| 订单到成交复盘 | `execution`、`portfolio` | order/fill/reconciliation commands/queries | Orders、Activity、Review |
| Agent 辅助研究 | `agent` + `application` | run/events/approval/campaign DTO、SSE | Copilot sidecar、Agent Console |
| 运行状态 | `platform` 技术设施 + 各能力 outcome | 健康、数据质量、任务结果 projection | Platform、全局状态条 |

### 5.3 合同策略

每个核心页面先列出它需要回答的问题，再核对现有 API：

1. 已有字段足够：只在前端增加 mapper，不改后端。
2. 已有多个稳定 query：由 `application` 增加窄的用例级 projection，避免浏览器自行拼装一致性。
3. 缺少用户可解释信息：由拥有该事实的能力包提供 typed 字段，再通过 application/apps 穿透。
4. 缺少写动作：复用现有 command，不为 UI 新建旁路写入。
5. 任何涉及时间、因子、回测、信号或研究证据的新增查询继续 fail closed，并传播 knowledge date、publication cutoff 和 source snapshot。

当前不新增 GraphQL、BFF 微服务、事件总线或通用 schema renderer。现有模块化单体和 typed HTTP DTO 足以完成产品。

## 6. 统一里程碑

### P0 — 事实收口与集成基线（3–5 人日）

目标：消除“后端完成、前端完成、产品却没完成”的状态歧义。

后端：

- 对 `codex/r5-governed-agent@a971a253` 做合并前审查，确认 38/38 证据与 `main` 当前差异。
- 合并或重放 R5 到新的集成分支；不在此阶段启用生产模型或扩大权限。
- 建立核心页面到现有 API/DTO 的清单，标出复用、mapper、窄 projection、真正缺口四类。
- 更正旧路线图的 R4/R5 状态和文档职责。

前端：

- 执行前端专项 M0：冻结批准原型、固定字体/数据/时间/视口、修复 route 与视觉审计口径。
- 把 33 条路由、28 个原型、31 个页面合同和 79 个 overlay 汇总成一张交付台账。
- 明确 `/research/alpha` 的正式路由与验收归属。

退出条件：

- 每个 P1—P4 页面都有后端 provider、API 合同、前端 owner、原型和完成状态。
- R5 分支处置结论明确，主线与计划不再互相矛盾。
- 视觉 diff 超阈值会真正令门禁失败。

### P1 — 统一 Shell 与 Decision Spine（3–5 人日）

目标：先让整个产品看起来、操作起来像同一个专业工作站。

- 恢复 Rail 56、Header 68、Status 24 和七类页面 Shell 的冻结几何。
- 建立唯一 App Shell、Page Header、Context Strip、workspace grid 和 overlay host。
- 实现全局 Decision Spine：当前上下文、证据来源、状态、阻塞原因和下一步动作在页面间连续传递。
- 保留现有 token 与组件底座，不引入第二套设计系统。
- 后端只冻结全局状态、市场日期和 readiness 的现有合同，不为 Shell 增加业务聚合层。

退出条件：Home、Trading Overview、Research、Agent Console 四个代表页在 desktop/compact/narrow 下达到几何阈值；mock/live Shell 完全同构。

### P2 — 日常决策与交易闭环（10–15 人日）

目标：交付第一个可每天持续使用的产品切片。

页面范围：

- Home：今日状态、数据 readiness、待复核事项和风险摘要。
- Trading Overview：Daily Decision V3 的 Ready/Review/Blocked 主工作面。
- Signals：信号证据、目标仓位、可执行仓位和阻塞原因。
- Portfolio：当前/目标/优化/可执行组合对比与归因。
- Risk：约束、风险预算、压力情景和处置说明。
- Orders/Activity：建议到订单、成交、持仓和对账的追踪。

后端工作仅限：

- 核对并复用 R4/G3 的 Daily Decision、portfolio/risk projection 和 execution readers。
- 如果页面需要跨多个一致性快照，增加用例级 display projection；不复制组合、风险或账本计算。
- 补充精确的 loading/empty/blocked/stale/error 语义和 as-of/snapshot 字段。

退出条件：用户能在 live 模式完成“查看 readiness → 理解建议 → 复核风险 → 形成订单 → 查看成交/偏差”的完整路径；页面无 live 占位和 prototype-only 核心 overlay；关键结果可追溯到同一 snapshot。

### P3 — 研究到策略与 Agent 闭环（12–18 人日）

目标：把已有 R3 与 R5 变成连续的研究工作面，而不是散落页面和聊天窗口。

页面范围：

- Research/Alpha：因子状态、衰减、覆盖、IC、异常和候选发现。
- Strategy Studio：StrategySpec/DSL 草案、编译诊断和差异预览。
- Experiments/Backtests：实验计划、运行、结果、可复现证据和失败恢复。
- Review/Publish/Reactivate：审查证据、holdout claim、版本和状态迁移。
- Agent Console/Copilot：Evidence、Author、Campaign、Approval、Episode 和 shadow briefing。

后端工作：

- 以合并后的 R5 API/SSE/CLI 为唯一 Agent 合同，flags 默认关闭并按能力独立开启。
- 复用 R3 experiment/holdout/ledger 和策略治理，不在 Agent 内复制 compiler、backtest 或统计裁判。
- 只为产品缺失的阅读 projection 补窄接口；策略发布、权重、订单和券商工具继续不存在。

退出条件：用户能完成“发现异常/机会 → 创建或修改研究草案 → 运行实验 → 审查证据 → 提交策略治理”的闭环；Agent 的每个 claim 有 evidence，所有写入有明确审批，关闭 Agent 后核心研究和交易仍可用。

### P4 — 市场发现与数据可靠性闭环（7–11 人日）

目标：让用户在采取研究或交易动作前，知道数据是否可信、市场发生了什么。

页面范围：

- Markets Overview、Watchlist、Instrument、Regime。
- Data Products、dataset quality、freshness、lineage 和恢复状态。
- Home/Research/Trading 中统一的数据质量与 stale 提示。

后端工作：

- 复用 R2 数据产品、quality、catalog、PIT 和 provider outcome。
- 为 watchlist/instrument/regime 增加必要的用例级读取合同，不新建行情平台。
- 不引入新的供应商或分钟级数据，除非现有数据无法完成已冻结页面合同，且单独批准。

退出条件：用户能从市场异常进入标的或因子研究，并在全链路看到 as-of、freshness、snapshot 和质量阻塞；任何 stale/缺失输入都不会被 UI 包装成正常建议。

### P5 — 个人 Beta 收口（6–9 人日）

目标：把 P1—P4 变成可恢复、可回归、可日常使用的版本。

- 完成跨仓库核心 E2E、OpenAPI/codegen、视觉、可访问性和状态矩阵门禁。
- 用真实或认证数据跑一次完整交易日流程和一次完整研究流程。
- 演练本地数据库备份/恢复、EOD/Agent 中断恢复、provider 不可用和前端断线重连。
- 固化启动、停止、数据更新、失败处置和恢复 runbook。
- 删除核心路径中的 live fallback、prototype-only 标记和不可解释通用错误。
- 建立轻量产品指标：任务成功率、完成时长、blocked 原因、恢复成功率、视觉回归和用户返工点。

退出条件：连续 5 个模拟或真实交易日核心流程无 P0/P1 产品阻塞；一次从备份恢复后可继续工作；用户无需进入 CLI 或数据库理解正常业务状态。

### 投入汇总

| 阶段 | 估算 |
|---|---:|
| P0 事实与集成 | 3–5 人日 |
| P1 Shell | 3–5 人日 |
| P2 日常决策与交易 | 10–15 人日 |
| P3 研究与 Agent | 12–18 人日 |
| P4 市场与数据 | 7–11 人日 |
| P5 个人 Beta | 6–9 人日 |
| 合计 | **41–63 人日** |

单人顺序执行时，建议每个阶段只保留一个正在进行的垂直切片。P0—P2 约 16–25 人日即可先得到真正有日常价值的核心产品，不必等待所有页面完成。

## 7. 首批执行 Backlog

| 优先级 | ID | 任务 | 主要仓库 | 完成证据 |
|---|---|---|---|---|
| P0 | ROADMAP-001 | 本文成为当前执行事实源，旧文档标记历史/长期职责 | ditto | 文档链接与状态一致 |
| P0 | R5-INTEGRATE-001 | 审查并合并 R5 完成分支 | ditto | review 无阻塞、CI/arch/PIT/release evidence 通过 |
| P0 | CONTRACT-001 | 核心页面 × API × provider 台账 | 两仓库 | 无未知 owner 或隐式前端拼装 |
| P0 | FE-GATE-001 | 冻结原型并让视觉/几何超阈值失败 | ditto-app | 代表页 RED 后修复为 GREEN |
| P0 | FE-SHELL-001 | 唯一 App Shell 与七类 workspace 骨架 | ditto-app | 四代表页跨视口通过 |
| P0 | TRADING-001 | Trading Overview 单一 PageView/PageModel | 两仓库 | mock/live DOM 同构、V3 三态完整 |
| P0 | TRADING-002 | Signals → Portfolio → Risk 上下文连续 | 两仓库 | 同 snapshot 的可追溯决策链 |
| P1 | EXECUTION-001 | Orders/Activity/对账闭环 | 两仓库 | 建议到 fill/position 偏差可解释 |
| P1 | RESEARCH-001 | `/research/alpha` 与研究主工作面 | ditto-app | 正式路由、状态、overlay、视觉门全过 |
| P1 | AGENT-UI-001 | Agent Console 按 Studio Shell 重构 | ditto-app | Evidence/Author/Campaign/Approval 可用，非聊天壳 |
| P1 | MARKET-001 | Markets/Data Products live 化 | 两仓库 | 无 live 占位，质量与 freshness 可见 |
| P1 | RELEASE-001 | 个人 Beta E2E 与恢复演练 | 两仓库 | P5 exit gate 证据包 |

推荐第一施工切片是 `FE-GATE-001 + FE-SHELL-001 + TRADING-001`。它能同时验证视觉方法、前端呈现架构和后端 display DTO 是否合理，失败成本最低。

## 8. 统一完成定义

一个页面或工作流只有同时满足以下条件才能标记完成：

1. 有明确用户问题、主动作、次动作和退出结果。
2. mock/live 使用相同 PageView、相同信息层级和相同交互结构。
3. loading、empty、stale、blocked、failed、partial、ready 状态都有设计和测试。
4. live 数据来自 typed API；页面不直接拼接多个可能不一致的快照。
5. 所有决策证据显示 as-of、snapshot、来源和不确定性；PIT 查询继续 fail closed。
6. 核心 overlay 真实可用，不以 prototype-only 占位通过。
7. desktop/compact/narrow 的几何与像素差异在冻结阈值内。
8. 键盘、焦点、颜色语义和 A 股红涨绿跌规则通过门禁。
9. 后端目标测试、前端目标测试、跨仓库 E2E 和文档状态一致。
10. 用户能从入口完成任务并理解结果，不需要查看日志、CLI 或数据库。

## 9. 明确不做

为避免过度设计，P0—P5 明确不做：

- 登录体系、复杂认证、RBAC、组织/角色/权限矩阵。
- 多租户、租户数据隔离、机构审计门户。
- 微服务拆分、Kubernetes、服务网格、事件总线或独立 BFF。
- 通用 LLM Gateway、多 Agent 生产编排、开放 Web/RAG/MCP。
- 自动策略发布、自动下单、真实券商无人值守操作。
- 分钟级/逐笔数据、盘中交易、全球资产和多币种账户。
- 第二套设计系统、微前端、SSR、低代码页面引擎或移动端重做。
- 为追求“10/10 平台”而提前建设商业化、计费、客服或机构合规能力。

当前只保留最低必要基线：loopback/个人私有运行、secret 不进代码和日志、危险动作人工确认、数据备份可恢复。任何更复杂的安全或权限建设必须由新的真实用户场景触发并单独批准。

## 10. 后续 R6/R7 启动条件

R6 分钟级只有同时满足以下条件才进入详细设计：

- P5 个人 Beta 通过，日频核心流程连续稳定使用。
- 用户证据表明分钟级能显著改善具体决策，而不是仅增加数据频率。
- 日频 workload、PIT、回放和前端状态模型能够平滑扩展。
- 有明确的数据供应、存储、延迟、成本和恢复预算。

R7 全球资产与机构化保持冻结。多租户、RBAC、复杂隔离也随 R7 一并冻结；在产品仍服务单操作者时不进入 backlog。

## 11. 路线图维护规则

- 本文状态按用户闭环更新，不按代码提交数量更新。
- 每个任务只有在跨仓库验收证据存在后才能从“工程完成”变成“产品完成”。
- 专项计划可细化任务，但不得扩大本文的产品边界和非目标。
- 新需求先放入对应用户闭环；无法映射到核心工作流的需求默认不进入当前版本。
- 每完成一个 P 阶段，复核投入、用户反馈和后续阶段范围；不预先建设尚未被验证的抽象。
