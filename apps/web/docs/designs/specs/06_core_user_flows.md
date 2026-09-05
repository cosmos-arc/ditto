# Ditto 核心用户流程

> **版本**: v1.4
> **日期**: 2026-04-18
> **上游**: [01 产品信息架构](./01_product_information_architecture.md)、[02 核心页面蓝图](./02_core_page_blueprints.md)
> **下游**: [04 交互与状态规范](./04_interaction_state_spec.md)

---

## 1. 文档目标

定义 Ditto v1 的 5 条核心用户流程，覆盖 happy path + 关键错误分支。

Ditto 的本质是面向个人量化研究与实盘闭环的专业工作台，核心链路只有一条：

**Observe → Discover → Research → Validate → Execute → Monitor / Improve**

本文件将这条链路拆解为 4 条用户可感知的核心流程，明确每条流程的页面跳转路径、关键分支和已知断裂点。所有页面与路由均来自已有的信息架构（01）和页面蓝图（02），不引入新功能或新路由。

### 适用读者

- UI/UX 设计：理解页面间的跳转逻辑与上下文传递
- 前端实现：规划路由守卫、状态传递和导航组件
- 产品评审：验证流程完整性、发现遗漏环节

---

## 2. Flow A: 市场观察 → 研究分析 → 交易执行

### 概述

这是 Ditto 最高频的流程。用户从首页出发，经过市场扫描、标的下钻、研究分析，最终到达交易执行或风险监控。核心动词序列是 **scan → drill down → judge → act**。

### 2.1 Happy Path

```
/ (Home)
  │ Today Pulse / Decision Banner → 点击市场快照
  ▼
/markets (Cross-Market Overview)
  │ 扫描 6 宫格 Market Cards → 点击某市场 Card
  ▼
/markets/a-shares (A 股总览)
  │ Market Structure Map → 点击某行业/概念节点
  ▼
/instruments/[id] (Instrument Hub)
  │ 概览 / 行情 / 态势 Tab → "发送到研究"
  ▼
/research (Research Workspace)
  │ 因子 Monitor → 策略入口
  ▼
（后续进入 Flow B 或直接跳转 Trading）
```

**每步的核心判断与动作**：

| 步骤 | 页面 | 用户判断 | 主 CTA |
|------|------|---------|--------|
| 1 | Home Command Center | 今天有没有必须处理的？市场状态如何？ | 点击市场快照进入 Markets |
| 2 | Cross-Market Overview | 哪个市场/资产类别值得看？Risk-On 还是 Risk-Off？ | 点击 Market Card 进入单市场 |
| 3 | A 股总览 | 哪个板块/主题最强？哪个标的需要进一步看？ | 点击 Map 节点进入 Instrument Hub |
| 4 | Instrument Hub | 这个标的状态如何？基本面/态势是否支持进一步研究？ | 发送到研究 / 加入观察 |
| 5 | Research Workspace | 因子健康度如何？最近研究进展怎样？ | 进入因子分析 / 策略 Studio |

### 2.2 关键分支

#### 分支 A1: Cross-Market 发现异常

```
/markets (Cross-Market Overview)
  │ Right Rail 风险预警出现 critical 级别条目
  ▼
/trading/risk (Risk Center)
  │ 查看 Active Breaches / Incident Timeline
  ▼
返回 /markets 或直接进入 /trading
```

**触发条件**: Right Rail 风险预警显示 critical 状态（参见 04 交互规范 critical 层级）。此分支绕过研究流程，直接进入执行监控。

#### 分支 A2: Instrument Hub → 加入观察

```
/instruments/[id] (Instrument Hub)
  │ "加入观察" CTA
  ▼
/markets/watchlist (Watchlist)
  │ 标的被添加到观察列表，后续可批量处理
  │ 单击标的 → Instrument Hub（继续研究）
  │ 批量选择 → Screener（进一步筛选）或 Research（加入标的池）
```

**说明**: 用户判断当前标的需要持续跟踪但暂不研究。Watchlist 是沉淀层，不阻断主流程。用户可从 Watchlist 回流：单击标的跳转到 Instrument Hub 继续研究，批量选择后可发送到 Screener 进一步筛选或加入 Research 标的池。

#### 分支 A3: Instrument Hub → 图表分析（内部 Tab）

```
/instruments/[id] (Instrument Hub)
  │ 切换到"图表分析" Tab
  ▼
/instruments/[id]?tab=chart-analysis
  │ 在 Instrument Hub 内做深度技术分析（原 Chart Lab 已降级为内部 Tab）
```

**说明**: Chart Lab 已降级为 Instrument Hub 的内部 Tab（图表分析），不再是独立路由 `/markets/chart-lab`。用户在标的详情页内直接切换 Tab 即可进入图表分析环境，完成分析后无需页面跳转。

#### 分支 A4: Home 直接跳转信号/订单

```
/ (Home)
  │ Pending / Next Actions 显示待处理信号或待复核订单
  ▼
/trading/signals (Signals Inbox) 或 /trading/orders (Orders Ledger)
```

**触发条件**: 首页 Decision Banner 或 Pending 区出现高优先级待办。此分支绕过市场观察和研究，直接进入执行层。

#### 分支 A5: Markets → Screener 精细筛选

```
/markets (Cross-Market Overview)
  │ 需要更精细的筛选条件
  ▼
/markets/screener (Markets Screener)
  │ 多维筛选 → 结果表 → Compare Drawer → Instrument Hub
```

**说明**: 当 6 宫格概览不足以定位目标标的时，用户切换到 Screener 做多条件筛选。Screener 的结果可批量发送到 Universe / Watchlist / AI Copilot Sidecar / Strategy Studio。

### 2.3 断裂点（已知）

#### BP-A1: Market 发现 → Research 的上下文断裂 ✅ 已修复

**位置**: `/instruments/[id]` "发送到研究" → `/research`

**问题**: Instrument Hub 到 Research 的跳转缺乏上下文传递。

**修复方案**: "发送到研究"现在携带标的上下文，采用跨域上下文传递协议（见 §8）。完整流程：

1. 用户在 Instrument Hub 点击"发送到研究"
2. URL 携带上下文参数：`/research?ctx[instrument]=600519&ctx[action]=show-related-factors`
3. Research Workspace 接收参数后：
   - Factor Monitor Table 自动筛选该标的关联因子
   - Analysis Band 高亮相关 IC/correlation 数据
   - 若该标的已关联策略，在 Recent Runs 中高亮相关回测
4. URL 栏显示 `/research`（简洁），但内部状态通过 URL 参数初始化

**状态**: 已修复（v1.1）— 见 §8 跨域上下文传递协议

---

## 3. Flow B: 因子发现 → 策略构建 → 回测验证 → 信号生成

### 概述

这是 Ditto 的研究闭环核心。用户从因子诊断出发，经过策略构建、回测验证，最终产出可执行的交易信号。核心动词序列是 **diagnose → compose → validate → activate**。

### 3.1 Happy Path

```
/research (Research Workspace)
  │ Factor Monitor Table → 点击某因子
  ▼
/research/factors/[id] (Factor Analysis)
  │ IC/IR 诊断 → "加入回测"
  ▼
/research/strategies/[id]/studio (Strategy Studio)
  │ Form / Code 模式构建策略 → 保存 → 提交回测
  ▼
/research/backtest/[id] (Backtest Result)
  │ NAV / MDD / 归因分析 → 指标达标
  ▼
策略进入信号生成
  ▼
/trading/signals (Signals Inbox)
  │ 确认信号 → 生成订单
```

**每步的核心判断与动作**：

| 步骤 | 页面 | 用户判断 | 主 CTA |
|------|------|---------|--------|
| 1 | Research Workspace | 哪些因子在退化？哪些表现好？有没有待审事项？ | 点击因子进入分析 |
| 2 | Factor Analysis | IC/IR/decay/turnover 是否达标？相关性如何？ | 加入回测 / 加入实验 |
| 3 | Strategy Studio | 策略逻辑是否正确？参数是否合理？ | 保存 → 校验 → 提交回测 |
| 4 | Backtest Result | Sharpe/MDD/Win Rate 是否满足要求？归因是否合理？ | 导出报告 / 启用信号 |
| 5 | Signals Inbox | 信号是否可信？风险检查是否通过？ | 确认 → 生成订单复核 |

### 3.2 关键分支

#### 分支 B1: 回测指标不达标

```
/research/backtest/[id] (Backtest Result)
  │ Sharpe / MDD / Win Rate 未达标
  ▼
/research/strategies/[id]/studio (Strategy Studio)
  │ 调整参数或策略逻辑 → 重新提交回测
  ▼
新的 /research/backtest/[id]
```

**触发条件**: Backtest Result 的 KPI Strip 中关键指标低于用户设定的阈值。这是最常见的研究迭代循环。

**状态关联**: 回测任务处于 `running` 状态时，Research Workspace 的 Recent Runs 区应持续显示进度（参见 04 交互规范 L3 Running Feedback）。

#### 分支 B2: 因子退化处理

```
/research/factors/[id] (Factor Analysis)
  │ Decay 诊断显示因子退化
  ▼
/research/experiments (Experiments)
  │ 将退化因子加入实验 → 测试改良版本或替代因子
```

**触发条件**: Factor Analysis 的 KPI Strip 显示 decay 值超过阈值，或 2x2 Diagnostics 的 decay 图呈现明显下降趋势。

**说明**: 实验是因子退化的标准处理路径，不是临时补救措施。

#### 分支 B3: 多因子组合策略

```
/research/factors/[id] (Factor Analysis)
  │ "加入实验" → 多个因子组合
  ▼
/research/experiments (Experiments)
  │ 创建多因子实验 → 运行对比
  ▼
实验结果 → 提取最优组合 → Strategy Studio
```

**触发条件**: 单因子策略不足以满足要求，需要多因子组合优化。Experiments 页面提供多因子组合的对比实验环境。

#### 分支 B4: 策略需要 Regime 适配

```
/research/strategies/[id]/studio (Strategy Studio)
  │ 策略逻辑需要区分市场 Regime
  ▼
/research/regime (Regime)
  │ 查看/切换当前 Regime 定义 → 回到 Studio 添加条件分支
```

**说明**: Regime 页面为策略构建提供市场环境分类参考。Strategy Studio 中可以基于 Regime 条件设置不同的策略参数。

#### 分支 B5: 策略回测 → AI 解读

```
/research/backtest/[id] (Backtest Result)
  │ "发送 AI 解读" CTA
  ▼
AI Copilot Sidecar（全局，当前页面唤出） — Strategy Draft 模式
  │ AI 分析回测结果 → 给出改进建议
```

**说明**: 用户对回测结果不确定时，可唤出 Copilot Sidecar 借助 AI 辅助解读。此分支连接 Flow C。

### 3.3 断裂点（已知）

#### BP-B1: Backtest → Signal 的激活断裂 ✅ 已修复

**位置**: `/research/backtest/[id]` → `/trading/signals`

**问题**: 回测通过后缺少从回测到信号生成的直接路径。

**修复方案**: 02 核心页面蓝图 §8 Backtest Result 已增加一级 CTA "启用信号"。完整流程：

1. 用户在 Backtest Result 页面查看 NAV/MDD/Sharpe 等指标
2. 指标达标时，"启用信号" CTA 可点击（灰色时悬停提示"关键指标未达标"）
3. 点击后弹出确认对话框，显示策略关键参数、风险指标和预估信号数量
4. 确认后策略状态变为 `signal-active`
5. 自动跳转至 `/trading/signals`，筛选该策略的信号
6. Signals Inbox 的 Signal Table 中显示来源标注 `source: 策略信号`
7. Home 的 Pending 区显示新的待复核信号

**状态**: 已修复（v1.1）— 02 蓝图 + 本文档同步更新

#### BP-B2: Research Workspace → Strategy Studio 的入口不明确

**位置**: `/research` → `/research/strategies/[id]/studio`

**问题**: Research Workspace 的主 CTA 包含"新建回测""新建实验""进入因子分析"，但缺少显式的"新建策略"入口。用户可能需要先进入 Factor Analysis 再跳转到 Strategy Studio。

**影响**: 从研究到策略构建的路径依赖因子分析作为中间跳板，不够直接。

**建议修复**: Research Workspace 的 Research Header 中增加"新建策略"一级 CTA，直接创建空白策略并跳转到 Strategy Studio。

**修复优先级**: P2（有替代路径但体验欠佳）

### 3.5 Flow D: 风控异常 → 策略调整 → 回测验证（Improve 回路）

#### 概述

这是 Ditto 的闭环维护流。当 Risk Center 检测到异常时，用户回到 Research 调整策略参数，重新验证后更新信号生成规则。核心动词序列是 **detect → diagnose → adjust → revalidate → update**。

#### 3.5.1 Happy Path

```
/trading/risk (Risk Center)
  │ Active Breaches 或 Stress Test 显示异常
  ▼
/trading/risk — 选择异常指标 → drill down 到归因分析
  │ 判断异常来源（市场 regime 变化 / 因子退化 / 仓位集中度过高）
  ▼
/research/strategies/[id]/studio (Strategy Studio)
  │ 调整策略参数 / 添加 regime 条件 / 修改风控约束
  ▼
/research/backtest/[new-id] (Backtest Result)
  │ 对修改后的策略运行回测 → 指标达标
  ▼
策略更新 → 旧信号失效，新信号生成
  ▼
/trading/signals (Signals Inbox)
  │ 确认新信号 → 执行
```

**每步的核心判断与动作**：

| 步骤 | 页面 | 用户判断 | 主 CTA |
|------|------|---------|--------|
| 1 | Risk Center | 哪些风控指标在恶化？是否需要调整策略？ | 查看归因 → 跳转 Strategy Studio |
| 2 | Strategy Studio | 策略哪里出了问题？需要调什么参数？ | 保存 → 提交回测 |
| 3 | Backtest Result | 修改后指标是否达标？与旧版本对比如何？ | 启用信号（替换旧版本） |
| 4 | Signals Inbox | 新信号是否比旧信号更合理？ | 确认 → 执行 |

#### 3.5.2 关键分支

##### 分支 D1: 异常来自因子退化

```
/trading/risk → 异常归因到某因子
  ▼
/research/factors/[id] (Factor Analysis)
  │ 诊断因子退化原因 → 加入实验
  ▼
/research/experiments → 测试替代因子
  ▼
实验成功 → 更新策略中的因子配置
```

##### 分支 D2: 异常来自市场 Regime 变化

```
/trading/risk → 异常归因到 regime 切换
  ▼
/research/regime → 查看/切换 regime 定义
  ▼
/research/strategies/[id]/studio → 添加 regime 条件分支
  ▼
/research/backtest/[new-id] → 验证新 regime 策略
```

##### 分支 D3: 回测指标未改善

```
/research/backtest/[new-id]
  │ 修改后指标仍未达标
  ▼
回到 Strategy Studio → 进一步调整或考虑弃用策略
  │
  ▼
策略状态变为 `retired`，信号生成停止
```

#### 3.5.3 与其他 Flow 的关系

- Flow D 是 Flow B 的**维护性回路**：Flow B 定义了"从零创建策略到启用信号"的路径，Flow D 定义了"策略运行后的持续改进"路径
- Flow D 与 Flow A 共享 Risk Center 入口（Flow A 分支 A1 也从 Cross-Market Risk 预警进入 Risk Center）
- Flow D 的终点是 Signals Inbox，与 Flow B/C 终点一致

### 3.6 Flow E: Regime 变化全局响应

#### 概述

这是 Ditto 的 Shell 级响应流程。Regime Indicator（参见 IA v2.0 §13.1）是 Status Bar 中的全局胶囊组件，当市场状态发生变化时触发通知，用户可从任何页面感知并响应。核心动词序列是 **detect → notify → decide → act**。

> **v1.3 新增**：此流程对应 IA v2.0 §13.1 Regime Indicator 全局组件。

#### 3.6.1 Happy Path

```
Regime Indicator（Status Bar 胶囊）
  │ 检测到 Regime 状态变化（Risk-On → Risk-Off 等）
  ▼
Shell 级通知条（页面顶部 banner）
  │ 展示变化摘要 + 置信度 + 驱动因素
  ▼
用户点击通知条 → 展开详情面板
  │ 查看 Regime 模型详情、切换历史、驱动因素
  ▼
用户决策：
  ├─ 忽略（关闭通知，继续当前工作）
  ├─ 调整策略 → /research/strategies/[id]/studio（添加/修改 Regime 条件分支）
  ├─ 暂停交易 → /trading/risk（检查持仓风险）
  └─ 查看详情 → /research/regime（深入分析 Regime 模型）
```

**每步的核心判断与动作**：

| 步骤 | 位置 | 用户判断 | 主 CTA |
|------|------|---------|--------|
| 1 | Status Bar 胶囊 | Regime 状态是否变化？ | 查看变化详情 |
| 2 | 通知条 banner | 这个变化是否影响我的策略/持仓？ | 展开 / 忽略 |
| 3 | 详情面板 | 变化是否显著？置信度如何？ | 调整策略 / 暂停交易 / 深入分析 / 忽略 |

#### 3.6.2 关键分支

##### 分支 E1: 忽略 Regime 变化

```
通知条 banner → 用户点击"忽略"或自动消失
  │ 继续当前工作流
```

**说明**: 不是所有 Regime 变化都需要用户响应。低置信度变化或用户策略已包含 Regime 条件时，用户可选择忽略。

##### 分支 E2: Regime 变化 → 调整策略（连接 Flow D）

```
通知条 → "调整策略"
  ▼
/research/strategies/[id]/studio
  │ 添加/修改 Regime 条件分支 → 提交回测
  ▼
后续进入 Flow D 回路
```

##### 分支 E3: Regime 变化 → 暂停交易（连接 Flow A/D）

```
通知条 → "暂停交易"
  ▼
/trading/risk (Risk Center)
  │ 检查 Active Breaches → 暂停信号生成
  ▼
后续进入 Flow D 改进回路
```

#### 3.6.3 与其他 Flow 的关系

- Flow E 是**唯一**由 Shell 级组件（而非页面内操作）触发的流程
- Flow E 的下游可连接 Flow D（调整策略/暂停交易）或 Flow B（新建 Regime 适配策略）
- Flow E 不改变当前页面上下文——用户从任何页面都能感知 Regime 变化，决策后跳转到对应工作流

---

## 4. Flow C: AI 辅助发现 → 审批 → 执行

### 概述

这是 Ditto 的 AI 加速流程。AI 能力以嵌入式形式分布在各业务域中：Copilot 作为全局 Sidecar 随时唤出，Alpha Explorer 作为 Research 域业务页承载因子发现（`/research/alpha`），Agent Console 归入 Platform 域（`/platform/agents`），Daily Brief / Priority Findings 在 Home 展示摘要与待审批事项。用户借助这些嵌入式 AI 进行市场发现、因子发现、策略草案生成和自动化研究，经审批后进入执行。核心动词序列是 **discover → research → draft → approve → execute**。

### 4.1 Happy Path

```
/ (Home) — Daily Brief / Priority Findings / Pending Approvals
  │ 查看最近 AI 发现、研究队列和待审批事项
  ▼
AI Copilot Sidecar（全局，任意页面唤出）
  │ Market Analysis 模式 → AI 产出市场分析结论
  ▼
用户采纳 AI 建议 → 发送到 Alpha Explorer / Strategy Studio / Watchlist
  ▼
/research/alpha (Alpha Explorer)
  │ 评估候选因子 → 样本外 / 相关性 / 换手 / 容量 / 行业暴露检查
  ▼
/platform/agents (Agent Console)
  │ 新建 Plan → Agent 运行 → Finding 产出
  ▼
Finding 需要 Approval → 用户审批
  ▼
审批通过 → 生成信号
  ▼
/trading/signals (Signals Inbox)
  │ 确认信号 → 生成订单
```

**每步的核心判断与动作**：

| 步骤 | 页面 | 用户判断 | 主 CTA |
|------|------|---------|--------|
| 1 | Home（Daily Brief / Priority Findings） | 最近 AI 有什么发现？有没有待审批事项？ | 查看 Finding / 进入 Alpha Explorer / 唤出 Copilot Sidecar |
| 2 | AI Copilot Sidecar | AI 分析是否可信？结论是否有价值？ | 保存结论 / 发送到目标工作区 |
| 3 | Alpha Explorer | 候选因子是否值得补测或入库？ | 深入候选 / 加入实验 / 申请采纳 |
| 4 | Platform/Agents | Agent Plan 是否合理？运行结果如何？ | 提交审批 / 重跑 |
| 5 | Agent Approval | Finding 是否值得执行？风险是否可控？ | 批准 / 拒绝 |
| 6 | Signals Inbox | AI 生成的信号是否可信？ | AI Review / Risk Officer / 确认订单复核 |

### 4.2 关键分支

#### 分支 C1: Approval 被拒绝

```
/platform/agents (Agent Console)
  │ Finding 审批被拒绝
  ▼
Agent 暂停
  │ 用户修改参数 / 调整 Plan
  ▼
重新提交 Agent 运行
```

**状态关联**: Agent Run 进入 `blocked` 状态（参见 04 交互规范 Agent 状态），Approval 进入 `rejected` 状态。Console 中必须明确显示拒绝原因，支持用户修改后重跑。

#### 分支 C2: Agent 运行失败

```
/platform/agents (Agent Console)
  │ Agent Run 状态变为 failed
  ▼
Detail / Tool Trace
  │ 查看工具日志 → 定位失败环节
  ▼
修复参数 → 重试
```

**状态关联**: Agent Run 进入 `failed` 状态。Tool Trace 应提供详细日志（参见 04 交互规范 Timeline 与 Trace 状态），用户可 drill-down 查看每一步的 raw output。

**说明**: Agent 运行失败不应只依赖 toast 通知（参见 04 交互规范 L3 Running Feedback），必须在 Console 中持续可见直到用户处理。

#### 分支 C3: AI 建议不采纳

```
AI Copilot Sidecar（全局，任意页面唤出）
  │ AI 分析结论不值得直接执行
  ▼
"保存为 Research Note" CTA
  ▼
结论归档到 Research Workspace 的 Notes 区
  │ 点击 Note → 跳转来源上下文（Instrument Hub / Backtest Result 等）
  │ Notes 区支持搜索/分类/关联对象导航
```

**说明**: AI 输出不应只有"采纳/拒绝"二元选择。不采纳的结论仍有归档价值，作为研究素材沉淀到 Research 域。Notes 区提供完整导航：搜索/分类/关联对象跳转，用户可从 Note 回到来源上下文继续工作。

#### 分支 C4: Copilot → Stock Discovery → Watchlist

```
AI Copilot Sidecar — Stock Discovery 模式
  │ AI 推荐标的一组标的
  ▼
批量 "加入 Watchlist" CTA
  ▼
/markets/watchlist (Watchlist)
```

**说明**: Copilot Sidecar 的 Stock Discovery 模式产出的是标的列表，而非策略。这类产出的自然去向是 Watchlist 或 Universe，而非直接进入交易。

#### 分支 C5: Copilot → Strategy Draft → Strategy Studio

```
AI Copilot Sidecar — Strategy Draft 模式
  │ AI 生成策略草案
  ▼
"发送到 Strategy Studio" CTA
  ▼
/research/strategies/[id]/studio (Strategy Studio)
  │ AI 草案作为初始代码/配置 → 用户微调 → 提交回测
```

**说明**: 这是 AI 辅助研究的深度路径。AI 产出的策略草案进入 Strategy Studio 后，后续流程与 Flow B 完全一致。注意：Copilot Sidecar 可在任意页面唤出，此处为在 Strategy Studio 页面唤出 Copilot 的典型场景。

#### 分支 C6: Alpha Explorer → Factor Adoption

```
/research/alpha (Alpha Explorer)
  │ Exploration Stream 产出候选因子
  ▼
Candidate Inspector
  │ 样本外 / 相关性 / 换手 / 容量 / 行业暴露 / 过拟合警告检查
  ▼
"申请采纳" CTA
  ▼
/platform/agents (Agent Console)
  │ Approval Panel 审批
  ▼
审批通过 → FactorArtifact
  ▼
/research/factors/[id] (Factor Analysis)
```

**说明**: 因子发现不再只是 Copilot 的泛模式。Alpha Explorer 是研究工作台，负责候选评估和实验追踪；Agent Console 只负责长任务、Trace、Artifact 和审批治理。

### 4.3 断裂点（已知）

#### BP-C1: AI Approval → Trading 的连接未定义 ✅ 已修复

**位置**: `/platform/agents` Approval 通过 → `/trading/signals`

**问题**: Agent Finding 审批通过后无自动化路径转化为 Signal。

**修复方案**: 02 核心页面蓝图 §14 Agent Console（`/platform/agents`）已增加"审批通过后自动生成信号"流程。完整自动化链路：

1. Agent Finding 审批通过
2. Finding 自动转化为 Signal，出现在 `/trading/signals` 的"待复核"队列
3. Agent Console 中 Finding 状态变为 `approved → signal-generated`
4. Home 的 Pending 区显示新的待复核信号
5. Signal 的 source 标注为 `ai-agent`，关联原始 Finding ID
6. 用户在 Signals Inbox 复核确认后进入订单执行流程

**状态**: 已修复（v1.1）— 02 蓝图 + 本文档同步更新

#### BP-C2: Home Priority Findings → 具体工作台的跳转不清晰

**位置**: Home（Priority Findings / Pending Approvals） → `/platform/agents`、`/research/alpha`、业务页或 Copilot Sidecar

**问题**: Home 底部的 Priority Findings 和 Pending Approvals 展示最近产出、待审批事项和研究队列，但从摘要卡片跳转到 Agent Console、Alpha Explorer、Signals Inbox 或 Copilot 会话的路径不够直观。

**建议修复**: Home 的每个摘要卡片增加明确的 drill-down 入口：
- Finding 卡片 → `/platform/agents`（定位到该 Finding）
- 待审批卡片 → `/platform/agents`（定位到该 Approval）
- Factor Candidate 卡片 → `/research/alpha`（定位到该 Candidate）
- 最近 Copilot 会话 → 唤出 Copilot Sidecar（定位到该 Session）

**修复优先级**: P2（有替代路径但体验欠佳）

---

## 5. 跨流程公共节点

以下页面是多条流程共享的关键节点，其设计质量直接影响所有流程的体验。

### 5.1 Home Command Center（/）

| 连接流程 | 角色 |
|---------|------|
| Flow A 起点 | Today Pulse / Decision Banner → Markets |
| Flow A 分支 | Pending → Signals / Orders（绕过研究直接执行） |
| Flow B 终点 | Recent Signals / Runs 显示回测产出 |
| Flow C 终点 | Daily Brief / Priority Findings 显示 AI 发现摘要（v2.1：原 `/ai` 总览内容归入此处） |

**设计要求**: Home 必须同时服务于"开始新工作"和"继续未完成工作"两种场景。Pending 区应按优先级排序（critical > warning > running > pending），跨域混合展示。Priority Findings 展示最近 AI / Agent 产出摘要，点击可跳转 `/platform/agents`、`/research/alpha` 或对应业务页。

### 5.2 Research Workspace（/research）

| 连接流程 | 角色 |
|---------|------|
| Flow A 终点 | Instrument Hub "发送到研究" 的目标 |
| Flow B 起点 | 因子发现与策略构建的入口 |
| Flow C 分支 | AI Research Note 的沉淀目标 |
| Flow C 核心 | Alpha Explorer 的上游入口，承接因子发现工作台 |

**设计要求**: Research Workspace 必须同时承接"从市场来的用户"（需要找标的关联因子）和"从 AI 来的用户"（需要查看沉淀的 Note 或进入 Alpha Explorer）。Factor Monitor Table 的筛选应支持按 instrument 关联过滤，Alpha 入口必须跳转 `/research/alpha` 而不是打开独立 AI 域。

### 5.3 Signals Inbox（/trading/signals）

| 连接流程 | 角色 |
|---------|------|
| Flow B 终点 | 回测达标 → 策略激活 → 信号生成 |
| Flow C 终点 | AI Approval 通过 → 自动生成信号 |
| Flow A 分支 | Home Pending → 直接跳转信号复核 |
| Flow D 终点 | 回测验证后的更新信号替换旧版本 |

**设计要求**: Signals Inbox 必须区分信号来源（策略信号 / AI 信号 / 手动信号），并在 Signal Detail 中展示来源上下文。这是全站执行闭环的最终关卡。

#### Signal 状态机与回退规则

Signal 完整生命周期（8 态，详见 [04 交互与状态规范 §15](./04_interaction_state_spec.md)）：

| 状态 | 说明 | UI 表现 |
|------|------|---------|
| pending | 等待处理 | 灰色标签 |
| reviewing | 用户正在复核 | 蓝色标签 + 详情面板展开 |
| approved | 已确认 | 绿色标签 |
| signal-generated | 已生成信号 | 青色标签 |
| order-submitted | 已提交订单 | 橙色标签 + 关联订单号 |
| completed | 订单已完成 | 绿色标签 + 成交确认 |
| expired | 信号已过期 | 灰色删除线 |
| failed | 失败 | 红色标签 + 失败原因 |

主链：`pending → reviewing → approved → signal-generated → order-submitted → completed`

**状态回退规则**：
- 订单提交失败（券商断连/余额不足/涨跌停阻断）: Signal 从 `order-submitted` 回退到 `reviewing`，Signal Detail 中展示失败原因 + "重试生成订单" CTA
- 用户取消已确认信号: Signal 从 `approved` 回退到 `reviewing`，需二次确认
- 订单部分成交: Signal 保持 `order-submitted`，标注部分成交数量
- 信号过期（超过有效期或标的状态变更）: Signal 从 `pending`/`reviewing`/`approved`/`signal-generated` 变为 `expired`，移入归档 Tab

> Signal 完整 8 态定义、UI 表现及通用状态映射见 [04 交互与状态规范 §15](./04_interaction_state_spec.md)。

### 5.4 Instrument Hub（/instruments/[id]）

| 连接流程 | 角色 |
|---------|------|
| Flow A 核心 | 市场扫描后的下钻目标 |
| Flow B 前置 | 研究前的标的判断 |

**设计要求**: Instrument Hub 是市场域和研究域的桥梁。Object Header 的一级 CTA（加入观察 / 发送到研究 / 打开图表分析）决定了用户下一步的去向。

### 5.5 Strategy Studio（/research/strategies/[id]/studio）

| 连接流程 | 角色 |
|---------|------|
| Flow B 核心 | 策略构建与编辑 |
| Flow C 分支 | AI 策略草案的接收目标（通过 Copilot Sidecar 或 Agent 模式生成） |
| Flow A 分支 | Screener 结果的批量导入目标 |

**设计要求**: Strategy Studio 必须支持多种入口上下文——空白创建（Flow B）、AI 草案导入（Flow C，通过 Copilot Sidecar）、Agent 自主候选（Flow C）、Screener 批量导入（Flow A 分支）。Manual / Guided / Agent 三模式必须共享同一 StrategySpec 预览和审批边界。

### 5.6 Risk Center（/trading/risk）

| 连接流程 | 角色 |
|---------|------|
| Flow A 分支 | Cross-Market 风险预警 → 直接进入 Risk Center |
| Flow D 起点 | 风控异常检测 → 归因分析 → 策略调整 |
| Flow D 终点 | 策略调整后回到 Risk Center 验证风控指标是否改善 |

**设计要求**: Risk Center 是 Improve 回路的起点和验证点。Active Breaches 必须支持归因分析（区分市场 regime / 因子退化 / 仓位集中度），并提供到 Strategy Studio 和 Factor Analysis 的直达路径。

---

## 6. 渐进展示策略

Ditto 的信息展示遵循"首屏给判断，滚动给细节，交互给深度"的原则。以下策略适用于所有 4 条核心流程。

### 6.1 展示层级

| 层级 | 角色 | 触发方式 | 典型内容 |
|------|------|---------|---------|
| 首屏 | 最高优先级信息 | 页面加载即可见 | Today Pulse、主工作面、待处理事项、KPI Strip |
| 滚动 | 次要信息 | 用户主动滚动 | 底部模块、历史数据、Timeline、Diagnostics |
| 交互展开 | drill-down 细节 | 点击/hover 触发 | Drawer、Inspector、Compare 面板、Detail 展开区 |
| Tab 切换 | 同一对象的多视角 | Tab 切换 | Object Hub 的概览/行情/态势 Tab、Platform/Agents 的 Plans/Runs/Findings Tab |

### 6.2 各流程的渐进展示节奏

#### Flow A: 市场观察 → 研究分析 → 交易执行

| 阶段 | 首屏 | 滚动 | 交互展开 |
|------|------|------|---------|
| Home | Today Pulse + Decision Banner + Pending | Priority Findings + Research Queue + My Workspace | 点击 Pending → 跳转 |
| Cross-Market | Market Cards + Context Bar + Scope Strip | Matrix + Macro Drivers + Bottom Tabs | Card 点击 → 单市场；Matrix 行 → drill-down |
| A 股总览 | Market Structure Map + Context Bar | ETF Matrix + Movers | Map 节点 → Instrument Hub |
| Instrument Hub | Object Header + Meta Strip + 默认 Tab 主视图 | Timeline / Linked Research | Tab 切换；Related 区点击 → 关联对象 |

#### Flow B: 因子发现 → 策略构建 → 回测验证 → 信号生成

| 阶段 | 首屏 | 滚动 | 交互展开 |
|------|------|------|---------|
| Research Workspace | Factor Monitor + Pulse Strip | Recent Runs + Experiments | 因子行点击 → Factor Analysis |
| Factor Analysis | KPI Strip + 2x2 Diagnostics | Stats Table / Corr Matrix / Notes | Tab 切换；"加入回测" → 弹窗确认 |
| Strategy Studio | Main Studio + Mode Switch | Logs / Validate / Dry Run | Inspector 展开；Snippets 选择 |
| Backtest Result | KPI Strip + NAV + Drawdown | Stats / Trades / Attribution / Diagnostics | Tab 切换；"加入对比" → Compare 模式 |
| Signals Inbox | Signal Table + Scope Strip | — | Signal 行点击 → Detail 面板 |

#### Flow C: AI 辅助发现 → 审批 → 执行

| 阶段 | 首屏 | 滚动 | 交互展开 |
|------|------|------|---------|
| Home（Priority Findings / Pending Approvals） | 最近产出 + 待审批摘要 | Research Queue | 卡片点击 → `/platform/agents`、`/research/alpha` 或业务页定位 |
| AI Copilot Sidecar | Conversation + Structured Output | — | Context/Evidence 展开；"发送到" → 目标选择 |
| Platform/Agents | Main Queue / Cards | — | Detail / Tool Trace 展开；Approval 弹窗 |

### 6.3 展示原则

1. **首屏不滚动即可决策**: 每个页面的首屏必须包含当前阶段的核心判断信息（参见 00 产品规格 L1/L2 密度准则）
2. **滚动是补充不是必须**: 如果用户不需要更多细节，首屏已足够完成当前判断
3. **交互展开不离开上下文**: Drawer、Inspector、Compare 都在当前页面内展开，不跳转新页面
4. **Tab 切换不改对象**: Object Hub 内的 Tab 切换只改变视角，不改变当前对象（参见 03 对象页规范）

### 6.4 新成员引导策略（Onboarding）

> **v1.1 新增**：针对内部团队新成员的渐进引导。

Ditto 作为内部工具，引导策略聚焦于"新成员快速上手团队现有工作流"，而非泛化的产品教程。

#### 引导三阶段

| 阶段 | 时间 | 触发条件 | 引导内容 | 实现方式 |
|------|------|---------|---------|---------|
| **冷启动** | 首次登录 | 首次进入 Ditto | 1. 设置默认密度偏好<br>2. 快速导航指引（6 个域的定位）<br>3. 团队工作流概览（"你的角色是 X，核心路径是 A→B→C"） | 内嵌引导 Modal（一次性） |
| **首周** | 登录后 7 天内 | 日常使用中触发 | 1. Tooltip 引导（首次访问某页面时高亮关键区块）<br>2. 推荐操作（"试试从 Screener 选一批标的加入观察列表"）<br>3. 快捷键提示（首次展示 kbd 快捷键） | 内嵌 Tooltip + Suggestion Toast |
| **稳定使用** | 7 天后 | 不再主动触发 | 1. Command Palette 帮助入口（输入 `?` 显示所有命令）<br>2. 上下文相关提示（如首次提交回测时提示成本配置） | Command Palette + 上下文 Banner |

#### 引导原则

1. **不打断工作流**：引导信息在非关键位置展示，不遮挡主工作面
2. **可关闭**：所有引导元素支持"不再显示"
3. **角色感知**：根据用户角色（01 IA §2.1）展示不同引导路径
4. **渐进减少**：冷启动 → 首周 → 稳定使用，引导强度递减至零

---

## 7. 断裂点修复建议

按优先级汇总所有已知断裂点及修复方案。

### P0: 核心闭环断裂（必须修复）

| ID | 断裂点 | 位置 | 修复方案 |
|----|--------|------|---------|
| BP-B1 | ~~Backtest → Signal 激活路径缺失~~ | `/research/backtest/[id]` | ✅ 已修复 — Backtest Result 增加"启用信号"CTA，02 蓝图 + 本文档同步 |
| BP-C1 | ~~AI Approval → Trading 连接未定义~~ | `/platform/agents` Approval 通过后 | ✅ 已修复 — Agent Console 增加自动信号生成流程，02 蓝图 + 本文档同步 |

### P1: 高频路径断裂（应当修复）

| ID | 断裂点 | 位置 | 修复方案 |
|----|--------|------|---------|
| BP-A1 | ~~Market → Research 上下文断裂~~ | `/instruments/[id]` → `/research` | ✅ 已修复 — 采用 §8 跨域上下文传递协议，Research Workspace 接收 URL 参数后自动筛选 |

### P2: 体验优化（建议修复）

| ID | 断裂点 | 位置 | 修复方案 |
|----|--------|------|---------|
| BP-B2 | Research → Strategy Studio 入口不直接 | `/research` → `/research/strategies/[id]/studio` | Research Workspace 的 Header 增加"新建策略"一级 CTA |
| BP-C2 | Home Priority Findings → 具体工作台跳转不直观 | Home（Priority Findings / Pending Approvals） → `/platform/agents`、`/research/alpha` 或 Copilot Sidecar | 每个摘要卡片增加明确 drill-down 入口，定位到具体 Session/Run/Finding/Candidate |

### 修复依赖关系

```
BP-B1 (Backtest → Signal)
  └─ 前置：需要定义策略的 signal-active 状态
  └─ 前置：Signals Inbox 需要支持 source 筛选

BP-C1 (AI Approval → Signal)
  └─ 前置：需要定义 Finding → Signal 的转化协议
  └─ 前置：Signals Inbox 需要支持 ai-agent source 标签
  └─ 关联：与 BP-B1 共享 Signals Inbox 的 source 筛选能力
  └─ v2.0：路由从 `/ai/agent` 迁移至 `/platform/agents`

BP-A1 (Market → Research 上下文)
  └─ 前置：需要定义 instrument → factors 的关联查询接口
  └─ 前置：Research Workspace 需要支持 URL 参数驱动的筛选模式
```

---

## 8. 跨域上下文传递协议（Context Transfer Protocol）

### 8.1 定义

Ditto 的多条核心流程涉及跨域跳转（如 Instrument Hub → Research、Copilot Sidecar → Strategy Studio）。为保证跨域跳转时上下文不丢失，定义统一的上下文传递协议。

### 8.2 协议格式

URL 参数格式：

```
/target-page?ctx[source]=<source_page>&ctx[<key1>]=<value1>&ctx[<key2>]=<value2>&ctx[action]=<target_action>
```

参数说明：

| 参数 | 说明 | 示例 |
|------|------|------|
| `ctx[source]` | 来源页面标识 | `instrument-hub`, `copilot`, `backtest` |
| `ctx[instrument]` | 标的 ID | `600519`（贵州茅台） |
| `ctx[strategy]` | 策略 ID | `strat-023` |
| `ctx[backtest]` | 回测 ID | `bt-1042` |
| `ctx[finding]` | Agent Finding ID | `find-089` |
| `ctx[run]` | Agent Run ID | `run-8842` |
| `ctx[candidate]` | Alpha 候选因子 ID | `fc-1042` |
| `ctx[mode]` | Copilot Sidecar 模式 | `market-analysis`, `stock-discovery`, `strategy-draft`, `factor-discovery` |
| `ctx[action]` | 目标页面应执行的动作 | `show-related-factors`, `load-draft`, `highlight-anomaly` |

### 8.3 已定义的跨域路径

| 路径 | URL 参数 | 目标动作 |
|------|---------|---------|
| Instrument Hub → Research | `ctx[instrument]=<id>&ctx[action]=show-related-factors` | Factor Monitor 筛选关联因子 |
| Copilot Sidecar → Strategy Studio | `ctx[source]=copilot&ctx[mode]=strategy-draft&ctx[action]=load-draft` | Studio 加载 AI 策略草案 |
| Agent Console → Alpha Explorer | `ctx[source]=agent&ctx[run]=<id>&ctx[candidate]=<id>&ctx[action]=review-alpha` | Alpha Explorer 定位 AutoResearch Run 和候选因子 |
| Alpha Explorer → Factor Analysis | `ctx[source]=alpha-explorer&ctx[candidate]=<id>&ctx[action]=open-adopted-factor` | Factor Analysis 打开采纳后的 FactorArtifact |
| Backtest → Copilot Sidecar | `ctx[source]=backtest&ctx[backtest]=<id>&ctx[action]=interpret` | Copilot Strategy Draft 模式加载回测上下文 |
| Screener → Strategy Studio | `ctx[source]=screener&ctx[instrument]=<ids>&ctx[action]=batch-import` | Studio 批量导入标的 |
| Risk Center → Strategy Studio | `ctx[source]=risk&ctx[strategy]=<id>&ctx[action]=adjust-risk` | Studio 定位到风控参数面板 |
| Agent Finding → Signals | `ctx[source]=agent&ctx[finding]=<id>&ctx[action]=signal-generated` | Signals 自动创建并筛选 |

### 8.4 实现约束

1. URL 参数仅用于初始化目标页面状态，URL 栏保持简洁（参数被消费后移除）
2. 目标页面必须支持无参数访问（向后兼容直接导航）
3. 上下文传递不改变目标页面的核心布局和交互模式
4. 参数验证失败时静默忽略，不显示错误

---

## Changelog

### 2026-05-02 — v1.4

- **[IA v2.1 同步]** Flow C 新增 `/research/alpha`，把因子发现从泛 Copilot 模式升级为 Alpha Explorer 工作台。
- **[流程补齐]** 新增 Alpha Explorer → Factor Adoption → Factor Analysis 分支。
- **[上下文协议]** 新增 `ctx[run]`、`ctx[candidate]`，补齐 Agent Console → Alpha Explorer 深链。
- **[Strategy Studio]** 同步 Manual / Guided / Agent 三模式的入口语义。

### 2026-04-18 — v1.3

- **[IA v2.0 同步]** Flow C 路由更新：`/ai` → Home Agent Findings 区块 + `/platform/agents`，`/ai/copilot` → AI Copilot Sidecar（全局），`/ai/agent` → `/platform/agents`
- **[IA v2.0 同步]** Flow B 分支 B5 路由更新：`/ai/copilot` → AI Copilot Sidecar
- **[IA v2.0 同步]** Flow A 分支 A5 Copilot 引用更新为 Copilot Sidecar
- **[IA v2.0 同步]** §5 跨流程公共节点：Home Agent Findings 区块说明更新
- **[IA v2.0 同步]** §6 渐进展示策略：Flow C 展示节奏更新为嵌入式 AI 架构
- **[IA v2.0 同步]** §7 断裂点修复表：BP-C1/BP-C2 路由引用更新
- **[IA v2.0 同步]** §8 跨域上下文传递协议：Copilot → Copilot Sidecar，新增 `factor-discovery` 模式
- **[新增]** Flow E: Regime 变化全局响应（§3.6）— Shell 级 Regime Indicator 触发 → 通知条 → 用户决策 → 跳转对应工作流
- 核心流程从 4 条扩展为 5 条

### 2026-03-31 — v1.1

- 修复 BP-B1: Backtest→Signal 激活断裂（S-1，P0）
- 修复 BP-C1: AI Approval→Trading 连接未定义（S-2，P0）
- 修复 BP-A1: Market→Research 上下文传递断裂（M-2，P1）
- 新增 Flow D: Improve 回路（Risk→Strategy→Backtest→Signal 维护性工作流）（M-9）
- 新增 §8 跨域上下文传递协议（Context Transfer Protocol）（M-12）
- 更新跨流程公共节点：增加 Risk Center 节点（§5.6）
- **[审计 Q3-7]** 新增 §6.4 渐进引导策略（冷启动/首周/稳定使用 3 阶段，4 条设计原则）

### 2026-03-31 — v1.0 初始版本

- 定义 3 条核心用户流程（Flow A / B / C）
- 识别 6 个已知断裂点，按 P0/P1/P2 分级
- 定义跨流程公共节点和渐进展示策略
- 所有页面和路由基于 01 产品信息架构和 02 核心页面蓝图推导
