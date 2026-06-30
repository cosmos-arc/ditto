# Ditto 战略定位与功能差距分析（2026-06-24）

> 本文是一次**源码级**的系统战略评估，目标是从"顶尖个人量化系统"的定位出发，回答三个问题：
> 1. 我们**真实**排在哪里？强在哪、弱在哪、和业界顶尖差多远？
> 2. 为什么**建了这么久，却从未投入使用**？
> 3. 通往"首次真实使用"的**最短可信路径**是什么？
>
> 方法：5 路并行 Explore agent 对 999 源文件 / 135k LOC、测试套件、CI、12 份架构文档、4 份历史对标文档、前端 ditto-app（37k LOC）做实证审计；所有结论带 `file:line` 证据。判断部分单列。

---

## 0. 摘要（TL;DR）

**核心论点：Ditto 的问题不是"差业界顶尖一截"，而是"长板极长、短板恰好卡在使用命门"的失衡。**

- 作为**工程/架构研究平台**：已是顶尖，多项指标**领先**多数开源同类（含 LEAN）——架构边界工具强制、源码零 `# type: ignore`、因子编译器、A股微结构精度、PIT 正确性。
- 作为**个人每天会打开用的量化系统**：**尚未达成**，卡在最后一公里——而那一公里被长期回避了。

**失衡的具象：** 一间全世界最精密的引擎室（架构 99.30/100），但**桥楼是空的**——前端从未连过真实后端、组合优化器不存在、归因是伪归因、回测 fill 系统性乐观。

**通往首次真实使用 = 两条并行关键路径同时收敛：**

| 关键路径 | 目标 | 关键交付 |
|---|---|---|
| **路径 A · 产品接入** | 让已有的后端能力**被用起来** | 前端接真实后端、eod 自动 publish-signals、降低日常摩擦 |
| **路径 B · 后端功能完整度** | 让被用的能力**值得信赖** | 组合优化器、成交量约束 fill、真实归因、真实数据 promotion |

> **两条路径同等重要、不可替代。** 只做 A 是给不完整能力镀金；只做 B 是又一轮"打磨引擎室、船不出港"。必须同时收敛到同一个"首次真实使用"汇合点。

---

## 1. 一句话定位裁决

> **Ditto 目前是一个"工程顶尖、A股微结构精确的因子/选股研究+回测平台"，但还不是"个人日常选股工具"。前者已可宣告胜利，后者是真正未完成的目标。**

这与项目自身最新的收敛口径一致（`capability-maturity.md`：initial-focus = A股 ETF daily research/backtest，reserved = live trading），但本文进一步指出：**即便在"研究/回测平台"这个已收敛的目标内，也存在三处一等公民级的功能缺陷**（组合优化、回测 fill 真实性、归因），它们直接决定了"研究结论是否可信"。

---

## 2. 真实画像：两面的 Ditto

### 2.1 工程与架构面 —— 领先（前 1%）

| 指标 | 实测值 | 评价 |
|---|---|---|
| 源码规模 | 999 文件 / **135,100 LOC** | 中大型，包分布合理（data 35.4k、application 31.8k 最大；kernel 1.15k 最小） |
| 测试规模 | 726 测试文件 / **207,292 LOC** | 测试/源码 = **1.53×**，远超行业均值 |
| 测试通过 | **8356 测试全绿**（41.5s，flaky=0） | 含 hypothesis 属性测试、inline-snapshot、golden e2e、真后端集成 |
| 类型纪律 | basedpyright strict 全量；**源码 `# type: ignore` = 0**；禁止"不必要 ignore" | 类型纪律最高分位 |
| 架构评分 | **99.30/100**（baseline 82）；37 契约全绿 | — |
| 边界治理 | 32 条 import-linter 契约 + 24 条自研 AST smell 检查（2169 行）+ **12 个包级边界单测** | **三层自动强制**，业界独有 |
| 技术债 | **全仓仅 2 条 TODO**；NotImplementedError 12 处全是合法分发分支 | 顶级水准 |

**世界级护城河（4 份历史对标文档反复确认）：**
- **因子表达式编译器**（Lexer→Parser→AST→Codegen + 编译期 PIT 安全 + 编译缓存）——超越 Qlib（单文件 AST）、LEAN（无因子编译器）。
- **架构边界机械化治理**——LEAN/Qlib/NautilusTrader 均靠人工 code review，Ditto 用工具强制。
- **L1-L4 四层数据质量引擎**——开源最全面。
- **A股微结构精度**（T+1 交收、涨跌停、收盘集合竞价、佣金/印花税/过户费）——LEAN 用通用模型。
- **PIT 防前视偏差**——D3 维度核查 **0 真违规**，9 处 `shift(1)` 全合规。

> **结论：在工程/架构维度，Ditto 不是"追赶者"，是"被追赶者"。继续在工程质量上攻坚已进入收益递减区**（项目自身 quality-eval 已承认）。

### 2.2 功能与产品面 —— 卡在命门

能力包成熟度（源码实证，非自评声明）：

| 能力包 | 真实成熟度 | 关键证据 |
|---|---|---|
| data | ✅ 真实可用 | Tushare/FRED/TDX 真实接入；CQRS 存储；L1-L4 质量；PIT 干净 |
| features | ✅ 真实可用（最强） | 表达式编译器 + 因子目录 + 物化 + IC/Fama-MacBeth 评估全套 |
| strategy | ✅ 真实可用 | Pipeline + DecisionStage + regime engine + 4 个真实模板 |
| portfolio | ⚠️ **部分（无优化器）** | 仅等权/逆波动/评分加权；约束顺序截断；**零 cvxpy** |
| risk | ✅ 真实可用 | PreTrade(5 规则) + Exposure + Drawdown + KillSwitch，真接入引擎 |
| execution | ⚠️ 部分（现实真实、券商仅 paper） | OMS/费用/对账扎实；**仅 PaperBrokerGateway**，external 空字面量 |
| backtest | ⚠️ 真实可用**但 fill 有缺陷** | T+1/涨跌停/集合竞价精确；**fill 无成交量约束 + 合约禁止部分成交** |
| analysis | ⚠️ 部分 | 研究 control-plane 真实；**experiments 目录为空、零归因实现** |
| application | ✅ 真实可用 | CQRS 编排层完整 |
| apps | ⚠️ 后端真实、**前端不可用** | 55 CLI + 22 API 路由真实；**ditto-app MSW-only、零写路径、半数 mock** |

**三处一等公民级缺陷（决定研究结论可信度，详见 §3）：**
1. **组合优化器完全不存在** —— 选股质量有硬上限。
2. **回测 fill 无成交量约束、合约禁止部分成交** —— 回测系统性乐观，结论不可信。
3. **归因是伪归因** —— 无法回答"为什么赚/为什么亏"，复盘失效。

---

## 3. 功能完善度深度对标（重点）

逐维度对标业界顶尖。差距定性采用五档：**领先 / 达标 / 骨架 / 无（有意 defer）/ 无（缺口）**。

| 维度 | Ditto 现状（源码实证） | 业界顶尖标杆 | 差距 | Ditto 排位 |
|---|---|---|---|---|
| **数据接入（源/质量/PIT）** | Tushare+FRED+TDX；L1-L4 质量；PIT 0 违规 | LEAN 30+ 源多路冗余 | 质量领先、**源数量与冗余少** | 🟢 领先（质量）/ 🟡 弱（冗余） |
| **因子/表达式/评估** | 编译器 + 物化 + IC/ICIR/Fama-Macbeth/正交化 | Qlib 单文件 AST | **超越 Qlib** | 🟢 领先 |
| **回测引擎（微结构）** | T+1/涨跌停/集合竞价/费用精确建模 | LEAN 通用模型 | A 股精度**领先** | 🟢 领先（A股） |
| **回测引擎（fill 真实性）** | **连续竞价无成交量约束**；[brokerage.py](../packages/execution/src/ditto_execution/brokerage.py) `all-or-nothing` 抛错；仅集合竞价 5% cap | backtrader Sizer/LEAN VolumeFillModel/zipline VolumeShareSlippage 均限成交量 | **一等公民缺陷** | 🔴 缺口 |
| **风控** | PreTrade(5) + Exposure + Drawdown + KillSwitch | 行业标准 | 达标 | 🟢 达标 |
| **执行/实盘** | **仅 PaperBrokerGateway**；external 空字面量 | LEAN 40+ broker、Nautilus 15+ | 巨大（**有意 defer**） | ⚫ 有意 defer |
| **组合优化** | [allocation.py](../packages/portfolio/src/ditto_portfolio/rebalancing/allocation.py) 3 个规则 Allocator；[constraints.py](../packages/portfolio/src/ditto_portfolio/rebalancing/constraints.py) 顺序截断（priority 串行，industry/turnover 各自线性 scale） | PyPortfolioOpt：MVO/Black-Litterman/风险平价/HRP；cvxpy 凸约束联合求解 | **无优化器** | 🔴 缺口 |
| **归因分析** | [attribution.py](../packages/features/src/ditto_features/evaluation/metrics/attribution.py)：`interaction_return=0.0` 硬编码、`timing=total-selection`（残差）、`annual_alpha=LS差`；analysis 包零归因 | Brinson 多期/Barra 因子回归/alphalens/pyfolio `perf_attrib` | **伪归因/骨架** | 🔴 缺口 |
| **参数寻优** | [specs.py](../packages/strategy/src/ditto_strategy/alpha/specs.py) 仅注释"为扫描 UI 和 walk-forward 提供元数据"；零实现 | Optuna TPE/CMA-ES、walk-forward、VectorBT grid/bayes | **无** | 🔴 缺口 |
| **多策略聚合** | 单 Pipeline 单账户单 [StrategyRunService](../packages/application/src/ditto_application/processes/execution/strategy_run_process.py) | strategy-of-strategies + 顶层资本分配 | **无** | 🔴 缺口 |
| **实时数据** | 纯批量（Prefect flow） | WebSocket event-driven（Nautilus） | 无（**有意 defer**） | ⚫ 有意 defer |
| **数据冗余/容灾** | A 股 tushare+tdx(本地文件)；FRED 单源无备用 | 多源交叉校验 + 自动 failover | 部分 / 无 | 🔴 缺口 |
| **产品化 / UI** | ditto-app：MSW 全拦截 + 零写路径 + 半数 mock 页 | 聚宽/米筐完整可用产品 | **晚期原型** | 🔴 缺口 |
| **架构/边界/类型/测试** | 99.30；0 type-ignore；8356 测试；三层边界强制 | 业界靠人工 review | **领先** | 🟢 顶尖 |

### 3.1 关键观察：排位呈"双峰分布"

把 13 个维度画成分布：

```
🟢 领先/顶尖（5）:  数据质量 · 因子引擎 · 回测微结构 · 风控 · 架构工程
🔴 缺口（6）:      fill真实性 · 组合优化 · 归因 · 参数寻优 · 多策略 · UI产品化
⚫ 有意 defer（2）: 实盘自动交易 · 实时数据
```

**这正是"失衡"的数据化呈现：** 系统在"研究/计算平面"全面领先，在"产品/决策平面"全面缺口。而个人量化的日常使用，恰恰活在后者。

### 3.2 与历史对标文档的差异（重要更正）

旧对标（`2026-04-07` / `2026-04-24`，自标 Historical）给 Ditto 综合 **6.8/10**、对标 LEAN 9.15/10。**该分数已过时且口径偏颇**——它把"实盘/多策略/实时"这些**项目已明确 defer 的维度**计入扣分，夸大了"差距"。

**本文修正后的判断：**
- 在**项目实际追求的目标域**（A股因子/选股 研究+回测 + 个人选股工具）内，Ditto 的工程面已达顶尖；
- 真实差距集中在**三条功能命门**（fill 真实性、组合优化、归因）+ **一个产品命门**（UI 接入），**而非"全面落后 LEAN"**。

---

## 4. 战略诊断："建了不用"的三层根因

"建设数月、从未投入使用"不是单点故障，是三层结构性原因叠加。

### 根因一：产品面缺失 —— 后端能力锁死在 API 层，到不了用户

后端 `/trade` 闭环**实际已完整存在**：
- 看推荐：`GET /trade/signals/latest`、`/trade/signals/{date}/intents`
- 记录决策：`POST /trade/fills`、`PUT /trade/intents/{id}/status`
- 复盘：`GET /trade/positions`、`/trade/pnl`、`/trade/deviation`（逐标的推荐 vs 实际偏差）、`/trade/comparison`（回测 vs 实际收益/Sharpe/成本）

**但前端 ditto-app 三个致命问题让它形同虚设：**
1. **dev 永远跑在 MSW mock 上，从不连真实后端**（`ditto-app/src/main.tsx` DEV 下 `worker.start`，13 域 handler 返回硬编码 fixture；无 `.env`、无 Vite proxy、`api-client.ts` 的 `VITE_API_BASE_URL ?? "/api"` 永远 fallback 到 dev server 自己 → 404）。**真实后端集成从未被验证。**
2. **整个前端零写入路径**（全树 `useMutation`/`apiClient.post|put|patch|delete` 命中数 = 0；`ConfirmSignalRequest`/`ValidateOrderRequest` 类型已定义却从未使用；trading overview"执行调仓"按钮**无 onClick**）。
3. **约半数列表页是硬编码 3 行 mock 常量**（portfolio/strategy list/backtest list/factor list/watchlist）。

> 一个不会 CLI 的人——**包括你自己作为"投资者"而非"工程师"时**——根本用不起来。后端再完整，能力也到不了使用者手里。

### 根因二：日常闭环有暗缝 —— 即使绕过前端走 CLI，摩擦依然很高

- [eod_flow](../packages/apps/src/ditto_apps/jobs/flows/eod.py) 串联了 摄取→物化→策略运行，但跑的是 **RESEARCH 模式且不调用 `signal_package_publisher`** → 自动 EOD pipeline **不会产出可交易信号**，`/trade/signals/latest` 永远空。用户必须每天**手动**补一步 `ditto strategy publish-signals`。
- 成交录入靠**手工 `POST /trade/fills`**（无券商/OMS 对接）。对一个个人用户 = 每天手工 POST 每笔成交。

> 这是"工程师工作流"，不是"投资者工作流"。日常使用的摩擦阈值必须降到"打开应用、点几下"。

### 根因三：范围漂移到负 ROI 区域

`capability-maturity.md` manifest 里 **80+ 条 addendum 集中在 execution/broker reconciliation / broker-event conformance**——而这是**项目已明确 defer 的实盘执行**的子问题。对"选股上线"贡献 ≈ 0，项目自身 production-readiness-eval（2026-06-14）已承认"工作重心与上线目标错配，继续在 execution/broker 矩阵投入是负收益"。

**与此同时，真正决定选股可信度的三件事被搁置：**

| 被搁置的命门 | 对"可信决策"的后果 |
|---|---|
| 组合优化器 | 选股质量有硬上限（等权天花板）；约束冲突无归一化保证 |
| fill 真实性 | 回测系统性乐观（大单可无限吃量），策略"虚假通过"；低流动性标的尤甚 |
| 真实归因 | 无法回答"为什么赚/亏"，复盘失效，学不到东西 |

### 根因的根因：完美主义引力井

三层根因背后是同一个模式：**系统持续被"架构完美、类型干净、边界无瑕"的工程引力吸引，回避了"功能闭环、产品可用、结论可信"这些更脏、更难、但才是使用命门的工作。** 这也解释了为什么"建了这么久"——精力投入在了**可被工具度量、可被 CI 验证的工程面**，而非**只能被真实使用验证的产品面**。

---

## 5. 目标重塑：二分目标 + 分阶段优先级

### 5.1 二分目标（解决目标长期漂移）

| 目标 | 状态 | 含义 |
|---|---|---|
| **目标 A · 研究+回测平台** | ✅ **已达成（可宣告胜利）** | A股因子/选股的研究、回测、IC 评估。工程顶尖、微结构精确、PIT 干净。**停止在此继续投入。** |
| **目标 B · 个人日常选股工具** | ❌ **真正未完成（本次聚焦）** | 打开就看到真实数据的可信选股、合理的组合构建、能记录决策、能复盘归因。 |

> 二者的关键区别：目标 A 的成功标准是"测试绿、架构分高"（已被工具验证）；目标 B 的成功标准是**"你在真实交易日基于它做出并跟踪了一个真实投资决策"**（只能被真实使用验证）。本文所有路线图服务于目标 B。

### 5.2 分阶段优先级（不是"永久 defer"，而是按阶段排期）

终止范围漂移的方式不是"永久放弃"，而是**显式分阶段**：明确每项能力属于哪个优先级阶段，文档/API 不得把低优先级描述为即将支持。

| 阶段 | 能力 | 定位 |
|---|---|---|
| **P0 · Wave 1（首次日常使用）** | A0 前端接入 · A1 eod publish · B0 组合优化器 · B1 fill 真实性 · B3 真实数据 promotion | 日频选股工具闭环，到达"首次真实使用" |
| **P1 · 高优先级阶段** | **盘中实时数据 + 信号候选** · B2 真实归因 · A2 fill 录入降摩擦 | 盘中决策能力 + 复盘深度 |
| **P2 · 中优先级** | 参数寻优（Optuna/walk-forward）· 第二数据源冗余 | 加固与调优 |
| **P3 · 低优先级远期** | **实盘自动交易（券商 adapter + 自动下单）** · 多策略聚合 | 远期阶段可做，优先级低；当前不追求 |

> ⚠️ **关键澄清（据反馈）：**
> - **盘中实时数据 + 信号候选是高优先级阶段（P1），不是 defer。** 它服务于盘中决策，是选股工具完整体验的重要组成，排在 Wave 1 之后、Wave 2–3 推进。
> - **实盘自动交易是分阶段远期目标（P3），不是永久放弃。** 最终阶段可以做，但当前最高优先能力不追求它——个人量化走手动交易（已有 `/trade/fills` 录入闭环）已可先用起来。

---

## 6. 通往"首次真实使用"的路线图（两条并行关键路径）

**汇合点定义（Definition of Done）：**
> 在一个真实交易日，你打开 ditto-app，看到**当天基于 promotion-ready 真实数据**生成的选股信号，系统用**真实组合优化器**给出建议组合，你记录下决策，事后能看 **deviation 复盘 + 因子归因解释"为什么"**。

到达此 DoD 需要路径 A 与路径 B **并行收敛**。下表为优先级矩阵。

### 6.1 优先级矩阵

| 任务 | 路径 | 影响 | 成本（单人估） | 是否关键路径 | 建议波次 |
|---|---|---|---|---|---|
| **A0 前端接真实后端** | A | 决定性（能力到不了用户） | ~1–1.5 周 | ✅ | Wave 1 |
| **A1 eod 自动 publish-signals** | A | 高（日常闭环暗缝） | ~2 天 | ✅ | Wave 1 |
| **B3 真实数据 promotion（RC1 hard-gate）** | B | 决定性（没有真实数据=没东西可看） | ~1 周（进行中） | ✅ | Wave 1 |
| **B0 组合优化器（cvxpy）** | B | 高（选股质量硬上限） | ~1.5–2 周 | ✅ | Wave 1 |
| **B1 成交量约束 fill** | B | 高（回测可信度） | ~1 周 | ✅ | Wave 1 |
| **A2 降低 fill 录入摩擦** | A | 中（投资者工作流） | ~2–3 天 | 🔶 | Wave 2 |
| **B2 真实归因** | B | 中高（复盘有效性） | ~1.5 周 | 🔶 | Wave 2 |
| **盘中实时数据 + 信号候选** | A+B | 高（盘中决策，**P1 高优先阶段**） | ~2–3 周 | 🔶 | Wave 2–3 |

> 关键路径（✅）= 缺它就到不了 DoD；🔶 = 加深信任/体验，DoD 后可继续。

### 6.2 路径 A · 产品接入（让能力被用起来）

**A0 · 前端接真实后端（最高优先，决定性）**
- 关闭 dev 默认 MSW 拦截；引入 `.env` + Vite proxy；`api-client.ts` 真实 `VITE_API_BASE_URL`。
- 实现写入路径：`record_fill`、`update_intent_status`、（可选）confirm signal。
- 去除 mock：signals inbox / orders / positions / deviation / comparison 页接真实 API。
- 评估并接上 OpenAPI codegen（`openapi-typescript` 已装但无脚本）——消除 `src/types/*.ts` 手写与后端 schema 静默漂移。

**A1 · eod 自动 publish-signals**
- [eod_flow](../packages/apps/src/ditto_apps/jobs/flows/eod.py) 切到 RECOMMENDATION 模式并调用 `signal_package_publisher`；或新增独立 daily cron：`ingest → materialize → publish-signals`。确保 `/trade/signals/latest` 永不空。

**A2 · 降低 fill 录入摩擦（Wave 2）**
- 从 signal 预填 fill 表单、一键确认；偏离推荐时提示。把"手工 POST"降级为"点几下"。

### 6.3 路径 B · 后端功能完整度（让能力值得信赖）

**B0 · 组合优化器（一等公民缺口）**
- ⚠️ **新增依赖 `cvxpy` 需你批准**（CLAUDE.md：新增依赖须人工批准）。**经业界查证确认 cvxpy 是正确选择**：它是 Python 凸优化事实标准（数学语法声明目标+约束，底层调度 ECOS/Clarabel/SCS/OSQP 等求解器），PyPortfolioOpt / riskfolio-lib / PortfolioLab 均建其上，Stanford Boyd 团队背书。对 Ditto **直接用 cvxpy、不引高层库**有两个硬理由：① **polars 兼容**——cvxpy 接口是 numpy/稀疏矩阵、不绑 pandas，而 riskfolio-lib / PyPortfolioOpt / skfolio 均 pandas 耦合，违反 Ditto polars-only 规则；② **自有 Allocator 抽象不被侵入**——高层库自带 Portfolio 对象会与 [allocation.py](../packages/portfolio/src/ditto_portfolio/rebalancing/allocation.py) 的 Allocator 边界冲突、违反 no-re-export 纪律。Wave 1 的 MVO + 线性/二次约束是纯凸 QP，cvxpy 几十行胜任。未来风险平价/Black-Litterman/HRP 同样直接基于 cvxpy 在自有 Allocator 内实现。
- 实现真实 Allocator：MVO（均值-方差）、风险预算/风险平价、（可选）Black-Litterman。
- 用**凸约束联合求解**替换 [constraints.py](../packages/portfolio/src/ditto_portfolio/rebalancing/constraints.py) 的顺序截断（满仓、行业上限、换手、个股上限一次满足，消除 `sum≠1` 反复破坏）。
- 保留等权作为 baseline 对照（A/B 验证优化器增益）。

**B1 · 成交量约束 fill（一等公民缺陷）**
- 重构 fill 合约，移除 [brokerage.py](../packages/execution/src/ditto_execution/brokerage.py) 的 `all-or-nothing` 强制（`raise FillProcessingError`），支持部分成交。
- 在 [AShareFillModel](../packages/backtest/src/ditto_backtest/simulation/fill.py) 连续竞价路径加入 participation-rate 成交量约束（参考 `ClosingAuctionFillModel` 已有的 `participation_rate_threshold × avg_volume_20d`）。
- 修复后回归所有 golden baseline（预期数值变化，需更新 golden 快照并记录"修复前后的容量/成本差异"作为证据）。

**B2 · 真实归因（Wave 2）**
- 用因子回归归因（Fama-French/Barra 残差 alpha）替换 [attribution.py](../packages/features/src/ditto_features/evaluation/metrics/attribution.py) 的伪归因（`interaction=0`、`timing=残差`、`alpha=LS差`）。
- 增加行业归因（Brinson 选股/交互/配置）。接入 `/trade/deviation` 复盘，让"为什么赚/亏"可答。

**B3 · 真实数据 promotion（进行中）**
- 推进 14 个必需数据集到 promotion-ready，满足 RC1 hard-gate（`rc1_real_data_acceptance.py --real-data --require-promoted` 返回 0）。这是"有真实数据可看"的前提。

### 6.4 两条路径如何汇合

```
Wave 1（并行，解除阻断 + 首次使用）:
  路径 A: A0 前端接后端 ──┐
  路径 B: B3 真实数据 promotion ──┤
         B0 组合优化器 ──────────┼──► 汇合点：首次真实使用（DoD）
         B1 成交量约束 fill ─────┘    （打开→看真实选股→优化器组合→记录）
  路径 A: A1 eod 自动 publish ──┘

Wave 2（深化信任与体验，DoD 后持续）:
  路径 A: A2 fill 录入降摩擦
  路径 B: B2 真实归因

Wave 2–3（P1 高优先阶段）:
  路径 A+B: 盘中实时数据 + 信号候选（盘中决策能力）
```

#### 关于"golden 快照变更"（重要：避免把改进当成回归改回去）

Ditto 用 golden 测试（`inline-snapshot` + [test_golden_baseline.py](../packages/backtest/tests/integration/test_golden_baseline.py)）把"一次完整回测的输出数值"钉死在快照文件里——回测跑完后断言 收益 / Sharpe / 持仓 / 换手 等指标等于之前记录的值。这些"golden 值"是**在当前 fill 模型（无成交量约束、all-or-nothing）+ 当前分配器（等权类）下记录的**。

- **B1（加成交量约束）后**：同一策略的大单会被 participation rate 截断 → 实际成交更少、冲击成本更高 → 收益/成本变化 → **钉死的 golden 值对不上 → 测试变红**。
- **B0（真优化器）后**：组合权重从等权变成优化后的权重 → 持仓/换手/收益变化 → **golden 值对不上 → 测试变红**。

**这个"红"是预期的、正确的**——它正在告诉你"行为变了"，而行为变正是你要的（fill 更真实、组合更优）。**要避免的反模式**：看到红就当回归，去调参/改代码把数值硬掰回旧 golden 值——那等于把刚加的成交量约束/优化器 silently 废掉（例如为了让 fill 数值匹配旧的乐观值，把 participation rate 放到 100%，约束形同虚设）。

**正确做法**：核对新行为合理后，用 `inline-snapshot --update`（或重新生成 golden baseline）**重新记录** golden 值，并把"修复前后差异"写进证据（例："加成交量约束后 Sharpe 从 1.8 降到 1.4——这 0.4 就是此前被隐藏的流动性成本"）。差异本身就是改进的量化证据。

---

## 7. 与已有对标文档的关系

| 文档 | 状态 | 本文处理 |
|---|---|---|
| `docs/reviews/2026-04-07-industry-benchmark-gap-analysis.md` | ⚠️ Historical | **口径过时**（把已 defer 维度计入扣分，6.8/10 偏低）。建议归档，本文 §3 取代其定位部分。 |
| `docs/reviews/2026-04-07-architecture-deep-dive-and-industry-benchmark.md` | ⚠️ Historical | 架构范式判断仍有效，可保留作历史参考。 |
| `docs/reviews/2026-04-24-comprehensive-industry-benchmark.md` | ⚠️ Historical | T1 全栈路线图已过时（目标已收缩）。建议归档。 |
| `docs/reviews/audit/2026-05-21-comprehensive-architecture-evaluation-v2.md` | ✅ 活跃 | 仍有效，与本文一致。 |
| `docs/reviews/2026-06-14-production-readiness-eval.md` | ✅ 活跃 | **本文与其"工作重心错配"诊断完全一致**，并给出可执行路线图。互补。 |
| `docs/reviews/2026-06-16-quality-eval.md` | ✅ 活跃 | 工程质量基线，与本文 §2.1 一致。 |
| `docs/architecture/capability-maturity.md` | ✅ 活跃 | 本文与之收敛口径一致；建议据本文 §5.2 补充分阶段优先级清单。 |

**本文的定位：** 不取代上述任一文档的专精内容，而是**统合定位裁决 + 功能差距 + 战略诊断 + 路线图**，作为"系统当前该往哪走"的单一权威参考。建议在 `MEMORY.md` 与 README 引用本文作为战略索引。

---

## 附录 A · 关键证据索引

**后端日常使用闭环：**
- CLI 入口：[strategy.py](../packages/apps/src/ditto_apps/cli/commands/strategy.py)（research/recommend/publish-signals）
- 信号发布持久化：[signal_package.py](../packages/application/src/ditto_application/processes/execution/signal_package.py)
- /trade 闭环 API：[trade_query_routes.py](../packages/apps/src/ditto_apps/api/routes/trade_query_routes.py)、[trade_command_routes.py](../packages/apps/src/ditto_apps/api/routes/trade_command_routes.py)
- EOD 暗缝：[eod.py](../packages/apps/src/ditto_apps/jobs/flows/eod.py)（RESEARCH 模式、不 publish）

**三处功能命门：**
- 组合优化：[allocation.py](../packages/portfolio/src/ditto_portfolio/rebalancing/allocation.py)、[constraints.py](../packages/portfolio/src/ditto_portfolio/rebalancing/constraints.py)
- fill 真实性：[fill.py](../packages/backtest/src/ditto_backtest/simulation/fill.py)、[brokerage.py](../packages/execution/src/ditto_execution/brokerage.py)（all-or-nothing）
- 伪归因：[attribution.py](../packages/features/src/ditto_features/evaluation/metrics/attribution.py)

**前端（独立项目 ditto-app）：**
- `ditto-app/src/main.tsx`（MSW dev 拦截）、`ditto-app/src/lib/api-client.ts`（无 env fallback）、`ditto-app/src/types/trading.ts`（已定义未用的写类型）

---

## 附录 B · 待确认的决策点（部分已据反馈更新）

1. **分阶段优先级（§5.2）** —— 已据反馈更新：盘中实时数据 + 信号候选归 P1 高优先阶段（非 defer）；实盘自动交易归 P3 低优先远期（非永久放弃）。请确认该排期。
2. **cvxpy 新依赖（B0）** —— cvxpy 是 Python 凸优化事实标准、业界最佳选择（见 §6.3 B0 与对话说明）。是否批准新增以解锁组合优化器？
3. **Wave 1 范围** —— 是否同意 A0/A1/B0/B1/B3 为首批并行攻坚。
4. **golden 快照变更策略（§6.4）** —— 已在 §6.4 详述：B1/B0 会改变回测数值，属预期改进，需重新记录 golden 值并保留前后差异证据，而非当回归掰回旧值。
