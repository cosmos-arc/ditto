# AI 能力增强设计：Agent Runtime + AutoResearch + 策略自动化

> 日期: 2026-05-01
> 状态: Draft
> 范围: AI 智能层全栈补强——从"精美仪表盘"到"有发动机的工作站"

---

## 1. 问题诊断

### 1.1 现状

Ditto 前端 AI 相关能力清单：

| 能力 | UI 层 | 类型层 | API 层 | 智能层 |
|------|:-----:|:-----:|:-----:|:-----:|
| Agent 工作流 (Plan→Run→Finding→Approval) | ✅ 完整 | ✅ 完整 | ⚠️ MSW mock | ❌ 空 |
| Agent 团队 (Analyst/Researcher/Trader/Risk/PM) | ❌ 仅文档描述 | ❌ 未定义 | ❌ | ❌ |
| Copilot Sidecar | ✅ 完整 | ✅ 完整 | ⚠️ MSW mock | ❌ 空 |
| Copilot Factor Discovery | ❌ | ✅ 类型定义 | ❌ | ❌ |
| Copilot Strategy Generation | ❌ | ✅ 类型定义 | ❌ | ❌ |
| Signal AI Interpretation | ❌ | ✅ 类型定义 | ❌ | ❌ |
| Agent Console (/platform/agents) | ✅ 完整 | ✅ 完整 | ⚠️ MSW mock | ❌ 空 |
| Home Agent Findings | ✅ 完整 | ✅ 完整 | ⚠️ MSW mock | ❌ 空 |
| Regime AI | ✅ 完整 | ✅ 部分 | ❌ | ❌ |

**结论**: UI 和交互设计 9.5+ 分，类型和 API 契约完整，但**所有智能层为零**——是一个精心设计的空壳。

### 1.2 业界对标

| 产品 | 核心能力 | 与 Ditto 的关系 |
|------|---------|---------------|
| TradingAgents (开源) | Multi-Agent 交易公司模拟 (基本面/技术/情绪→辩论→决策) | 直接对标 Ditto 的 Agent 团队设计，但可实际运行 |
| daily_stock_analysis (开源) | LLM 驱动 A/H/美股每日自动分析 + 推送 | Ditto 应有的每日自动化能力 |
| FinceptTerminal (开源) | 开源 Bloomberg 替代，AI Investor Personas + QuantLib | 工具箱路线，Ditto 走工作流编排路线 |
| Manara/Minara | AI 财务助手，50+ 数据源 + 自然语言交互 | 聊天式路线，Ditto 走专业终端路线 |
| Alpha-GPT (论文) | Human-AI 交互式 Alpha 挖掘 | 因子挖掘的人机共创范式 |
| WorldQuant BRAIN | Alpha 表达式→模拟→排行 | Alpha 挖掘平台的 UI/UX 标杆 |
| Karpathy AutoResearch | AI Agent 自主实验循环 (700 实验/2 天) | 因子挖掘+策略构建的全自动模式 |
| Capitalise.ai | 自然语言→策略→回测→部署 | 零代码策略构建 |

### 1.3 核心问题

Ditto 90% 的工程投入放在了最顶层（UI），底层（数据→特征→模型）几乎是空的。需要在已有数据管线 (tushare/MiniQMT) 之上构建智能层。

---

## 2. 架构设计

### 2.1 总体架构

```
┌─ 前端 (React + Vercel AI SDK) ────────────────────────────────┐
│  useChat / useCompletion / useObject → SSE 流式传输            │
│  ├── Copilot Sidecar — 对话式交互                              │
│  ├── Agent Console — Plan/Run/Finding 管理                    │
│  ├── Alpha Explorer — 因子挖掘可视化                            │
│  ├── Strategy Studio — 三种构建模式                             │
│  └── Signal Inbox — AI 信号解读                                │
├─ HTTP/SSE ────────────────────────────────────────────────────┤
│  FastAPI 后端                                                  │
│  ├── /api/ai/copilot/*     → Copilot 会话 + 流式               │
│  ├── /api/ai/agents/*      → Agent 管线 CRUD + 实时推送        │
│  ├── /api/ai/signals/*     → AI 信号解读                       │
│  ├── /api/ai/alpha/*       → Alpha 挖掘 (Copilot + AutoResearch)│
│  ├── /api/ai/strategy/*    → 策略自动构建                      │
│  └── /api/trading/signals  → 信号→订单                         │
│                                                                │
│  Agent Runtime (FastAPI 内部)                                   │
│  ├── Agent Orchestrator — 多 Agent 编排 + 调度                 │
│  ├── Tool Registry — 注册所有数据/分析工具                      │
│  ├── Agent 团队:                                               │
│  │   ├── Analyst Team (并行):                                  │
│  │   │   ├── FundamentalAnalyst                                │
│  │   │   ├── TechnicalAnalyst                                  │
│  │   │   └── SentimentAnalyst                                  │
│  │   ├── Research Team (对抗):                                 │
│  │   │   ├── BullResearcher                                    │
│  │   │   └── BearResearcher                                    │
│  │   └── Decision Team:                                        │
│  │       ├── TraderAgent                                       │
│  │       ├── RiskAgent                                         │
│  │       └── PMAgent                                           │
│  │                                                             │
│  Tool Layer (Agent 可调用的工具):                                │
│  ├── 数据工具: get_stock_quotes / get_financials / get_news / get_kline │
│  ├── 分析工具: calc_indicators / calc_factors / detect_patterns / analyze_sentiment │
│  └── 执行工具: create_signal / check_risk_limits / run_backtest │
│                                                                │
│  AutoResearch Engine                                            │
│  ├── Alpha Explorer — 因子自动挖掘 (Copilot + Autonomous)      │
│  ├── Strategy Builder — 策略自动构建 (Guided + Autonomous)     │
│  ├── Strategy Optimizer — 策略持续自优化                        │
│  └── Scheduled Runner — 定时任务调度 (每日/每周/事件触发)       │
│                                                                │
│  Data Layer (已有)                                              │
│  ├── tushare — 历史数据                                         │
│  ├── MiniQMT — 实时行情 + 执行                                 │
│  └── 通达信 — 交叉验证                                          │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent 工作流：完整管线

```
[触发] 用户提问 / 定时调度 / Regime 变化 / 因子退化
  │
  ▼
[Agent Orchestrator] 选择并调度 Agent 团队
  │
  ▼
[Analyst Team — 并行执行]
  ├── FundamentalAnalyst → 调用 get_financials / calc_factors
  ├── TechnicalAnalyst → 调用 get_kline / detect_patterns / calc_indicators
  └── SentimentAnalyst → 调用 get_news / analyze_sentiment
  │
  ▼
[Research Team — 对抗辩论]
  ├── BullResearcher → 综合看多论据
  └── BearResearcher → 综合看空论据
  │
  ▼
[TraderAgent] → 综合研判 → 生成 Finding (置信度 + 论据链 + 风险提示)
  │
  ▼
[RiskAgent] → 风控检查 (仓位/相关性/流动性)
  │
  ▼
[PMAgent] → 最终审批 → pending_approval (需人工) / auto_approved (低风险)
  │
  ▼
[输出]
  ├── Agent Console → Finding 列表 + 审批
  ├── Home Agent Findings → 摘要卡片
  ├── Signal Inbox → AI 信号解读 (审批通过后)
  └── Strategy Detail → 策略优化建议 (策略维护模式)
```

### 2.3 前端技术对接

前端使用 Vercel AI SDK (`ai` 包) 对接后端 SSE：

```typescript
// Copilot Sidecar — 流式对话
import { useChat } from 'ai/react'

const { messages, input, handleSubmit, isLoading } = useChat({
  api: '/api/ai/copilot/chat',
  body: { mode: 'research', context: { instrumentId, factorId } },
})

// Agent Finding 实时推送 — useObject
import { useObject } from 'ai/react'

const { object: finding } = useObject({
  api: '/api/ai/agents/runs/current/finding',
  schema: agentFindingSchema,
})

// Alpha Explorer — 流式探索结果
import { useChat } from 'ai/react'

const { messages } = useChat({
  api: '/api/ai/alpha/explore',
  body: { mode: 'copilot', constraints: { minIC: 0.03, maxTurnover: 5 } },
})
```

---

## 3. 模块 A：因子自动挖掘 (Alpha Explorer)

### 3.1 两种模式

| 模式 | 人类参与度 | 适用场景 | 触发方式 |
|------|:---------:|---------|---------|
| **Copilot 模式** | 高 (Human-in-the-Loop) | 定向深挖、人类引导探索 | 用户主动启动 |
| **AutoResearch 模式** | 无 (Fully Autonomous) | 广度探索、夜间巡检 | 定时调度 / Regime 变化触发 |

### 3.2 Copilot 模式交互

**入口**: Research Workspace 新增 tab "Alpha Explorer"，或 Agent Console 创建 Alpha 挖掘类型的 Plan。

**交互流程**:

1. 用户设置探索约束 (搜索空间、IC 阈值、相关性上限、宇宙范围)
2. Agent 实时展示探索流 — 每个候选因子的公式、IC、换手、相关性
3. 用户可随时干预: "为什么选这个?"、"深入探索这个方向"、"修改公式"、"暂停"
4. 帕累托前沿实时更新 (IC vs 换手散点图)
5. 被采纳因子自动进入参数优化阶段 (网格搜索 + Agent 微调)

**UI 组件**:

- **探索配置面板**: 搜索空间选择器、约束条件输入、策略选择 (深度优先/广度优先/随机)
- **实时探索流**: 卡片式候选因子列表，每张卡片含公式、IC 趋势 sparkline、操作按钮
- **帕累托前沿面板**: IC vs 换手散点图，已采纳用实心标记
- **参数优化子面板**: 参数网格表 + IC 提升对比 + 应用/手动调整按钮

**产出流向**:
- 采纳的因子 → Factor List (标记 "AI Generated" + 来源 Run ID)
- 采纳的因子 → Factor Analysis (完整 IC 诊断)
- 采纳的因子 → Experiment List (自动创建 A/B 实验)
- 所有发现 → Agent Console (Finding 记录)

### 3.3 AutoResearch 模式交互

**入口**: Agent Console → 新建 Plan → 类型选择 "Alpha 挖掘" → 模式选择 "自主研究"。

**交互流程**:

1. 用户给出极简目标 (可选: 自由探索 / 特定方向 / 约束条件)
2. Agent 完全自主运行，无需人类干预
3. 用户回来后查看 **AutoResearch Dashboard**

**Dashboard 内容**:

- **总览**: 实验总数、有效发现数、已采纳数、仍在审查数、最佳发现
- **研究路线图**: 阶段性决策记录 — Agent 探索了什么、发现了什么、为什么转向
- **发现清单**: 候选因子列表，按 IC 排序，含公式、指标、新颖度、与现有因子相关性
- **性能演进图**: 散点图 (实验编号 vs IC)，帕累托前沿连线

**Agent 自主决策点**:
- 探索方向选择 (基于前序实验的元学习)
- 路线放弃判定 (连续 N 次无改善)
- 深入方向选择 (检测到异常模式时)
- 参数优化策略 (网格搜索 / 贝叶斯优化 / 随机搜索)
- 终止条件 (达到实验上限 / 时限 / 目标 IC 已满足)

**审计性**: 所有决策记录在 "研究路线图" 中，用户可回溯 Agent 的每一步推理。

### 3.4 定时调度

| 调度 | 频率 | 模式 | 产出 |
|------|------|------|------|
| 因子健康巡检 | 每日 07:00 | AutoResearch (轻量) | 退化预警 → Home Agent Findings |
| Alpha 深度挖掘 | 每周 22:00 | AutoResearch (深度) | 新因子候选 → Agent Console |
| Regime 变化触发 | 事件驱动 | AutoResearch (定向) | 新环境因子适配建议 |

---

## 4. 模块 B：策略自动构建 (Strategy Builder)

### 4.1 三种构建模式

| 模式 | 人类参与度 | 输入 | 输出 | 适用场景 |
|------|:---------:|------|------|---------|
| **Manual** | 100% | 用户手动配置 | 策略草稿 | 专业用户、精细调优 |
| **Guided** | 中等 | 自然语言描述 + AI 逐步引导 | 可用策略 | 快速原型、半专业用户 |
| **Agent** | 低 | 高层目标 + 约束 | 回测验证的策略 | 自动化、非专业用户 |

### 4.2 Guided 模式 (Copilot 式)

**入口**: Strategy Studio → 新建策略 → "引导模式"。

**交互**: 左侧为对话面板 (类似 Copilot Sidecar 嵌入 Studio)，右侧 Inspector 实时预览策略配置。

**对话流程**:
1. AI 询问策略类型 (多因子选股/动量反转/事件驱动/自定义)
2. 用户描述意图 (如 "沪深300增强，偏质量低波，控制回撤")
3. AI 建议因子组合 + 权重 + IC 预测
4. 用户可调整 ("动量换成短期")
5. AI 建议风控参数 (基于用户的风险偏好描述)
6. 生成策略 → 可进入 Studio 精调 / 直接回测 / 保存草稿

**Inspector 实时预览**: 因子权重分布图、IC 预测、风控检查摘要、预计换手

### 4.3 Agent 模式 (全自动)

**入口**: Strategy Studio → 新建策略 → "Agent 模式"。

**用户输入** (极简):
- 目标: "年化 > 15%, 最大回撤 < 12%"
- 宇宙: 沪深300
- 约束: 不做空 / 换仓月度 / 单票 < 5%
- 实验预算: 50 次回测
- 可用因子: 全部 / AI 自动选择

**Agent 自主循环**:
1. 选择基线策略 (如等权重多因子)
2. 运行回测 → 评估是否达标
3. 不达标 → Agent 调整 (换因子/调权重/加风控/改参数)
4. 达标 → 运行稳定性验证 (不同时间段)
5. 通过 → 锁定为候选策略
6. 不通过 → 继续调整

**输出**:
- 策略完整配置 (因子 + 权重 + 风控 + 预处理)
- 全期 + 分期回测结果
- Agent 的决策日志 (为什么选这些因子、为什么调整权重)
- 风险点标注 (如 "2022 年 MDD 曾达 -13.1%")
- 操作按钮: 进入 Studio 精调 / 直接回测 / 采纳 / 拒绝

### 4.4 策略持续自优化 (Strategy Maintenance Agent)

**入口**: Strategy Detail → "启动自动优化"，或定时调度。

**Agent 持续监控**:
- 实际 Sharpe vs 预期 (滑动窗口)
- 各因子贡献变化 (衰减检测)
- Regime 适配性 (当前市场状态 vs 策略设计假设)

**产出 — 自优化提案**:
- 提案 A: 调整因子权重 (预测影响: Sharpe +0.08)
- 提案 B: 加入择时逻辑 (预测影响: MDD -1.2%)
- 提案 C: 替换退化因子 (来自 AutoResearch 新发现)

每个提案都有 "模拟回测" 按钮 — 用户可在审批前看到预测效果。

---

## 5. 每日自动化流程

| 时间 | Agent 任务 | 模式 | 产出位置 |
|------|-----------|------|---------|
| 06:00 | 数据健康巡检 | Scheduled | Home → Data Health |
| 07:00 | 因子健康巡检 | AutoResearch (轻量) | Home → Agent Findings |
| 08:00 | 持仓分析 | Agent 团队 (Analyst+Trader) | Signals → AI 解读 |
| 12:00 | 午间回顾 | Scheduled | Trading Overview |
| 15:00 | 收盘总结 | Scheduled | Trading Overview |
| 20:00 | 策略自优化 | AutoResearch (深度) | Strategy Detail → 提案 |
| 22:00 | Alpha 巡检 | AutoResearch (挖掘) | Agent Console → Finding |

---

## 6. Agent Console 增强

当前 Agent Console (/platform/agents) 已有 Plan→Run→Finding 的列表和审批 UI。需要增强：

### 6.1 新增 Agent 类型

| 类型 | 说明 | 新增 UI |
|------|------|---------|
| **Alpha 挖掘** | 因子自动发现 | AutoResearch Dashboard 视图 |
| **策略构建** | 策略自动生成+回测 | 策略构建活动流 |
| **策略优化** | 策略持续维护 | 优化提案列表 |
| **持仓分析** | 每日持仓 AI 分析 | Finding 增强 (含论据链) |
| **每日巡检** | 综合每日自动化 | 每日报告视图 |

### 6.2 Finding 类型扩展

当前 Finding 只有文本摘要。需要增加结构化 Finding：

```typescript
type AgentFinding =
  | TextFinding          // 现有: 文本 + 置信度
  | FactorCandidateFinding // 新增: 因子候选 (公式、IC、换手)
  | StrategyProposalFinding // 新增: 策略提案 (配置、回测结果)
  | OptimizationProposalFinding // 新增: 优化提案 (权重调整、预测影响)
  | RiskAlertFinding     // 新增: 风险预警 (因子退化、Regime 变化)
```

### 6.3 Agent 实时状态

Agent Console 的 Inspector Panel 需要展示：

- **活动流**: Agent 当前在做什么 (实时 SSE 推送)
- **工具调用追踪**: Agent 调用了哪些 tool、输入输出、耗时
- **论据链**: Finding 的完整推理过程 (可展开查看每步)
- **性能指标**: 本次 Run 的 token 消耗、耗时、调用的 tool 数量

---

## 7. 建设节奏

### Phase 1: Agent 跑起来 (2-3 周)

**目标**: 一个完整的 Agent Run 产出一个 Finding，前端展示真实数据。

| 步骤 | 任务 | 产出 |
|------|------|------|
| 1.1 | 后端: Agent Orchestrator + Tool Registry | Agent runtime 框架 |
| 1.2 | 后端: 实现 3 个数据 Tool | get_stock_quotes / get_financials / get_kline |
| 1.3 | 后端: 实现 3 个 Analyst Agent | 基本面/技术/情绪分析 |
| 1.4 | 后端: 实现 TraderAgent | 综合研判 → Finding 输出 |
| 1.5 | 前端: Vercel AI SDK 替换 Copilot MSW mock | Copilot Sidecar 接 SSE |
| 1.6 | 前端: Agent Console 接真实 API | Agent Console 展示真实数据 |
| 1.7 | 端到端验证 | Home Agent Findings 展示真实 Finding |

### Phase 2: Copilot + 对抗辩论 (2 周)

| 步骤 | 任务 |
|------|------|
| 2.1 | 实现 Bull/Bear Researcher (对抗辩论) |
| 2.2 | 实现 RiskAgent + PMAgent |
| 2.3 | Copilot 对接 Agent Runtime (用户提问触发 Agent 分析) |
| 2.4 | Signal AI Interpretation 对接 |
| 2.5 | Factor Discovery Copilot 模式 |

### Phase 3: Alpha Explorer + Strategy Builder (3-4 周)

| 步骤 | 任务 |
|------|------|
| 3.1 | Alpha Explorer — Copilot 模式 (Research Workspace 新 tab) |
| 3.2 | Alpha Explorer — AutoResearch 模式 (Agent Console 新类型) |
| 3.3 | Strategy Studio — Guided 模式 (对话面板 + Inspector 联动) |
| 3.4 | Strategy Studio — Agent 模式 (活动流 + 策略输出) |
| 3.5 | K 线模式识别 Tool (CNN / Kronos 微调) |
| 3.6 | 因子引擎 Tool (IC/IR 计算 + 衰减分析) |

### Phase 4: 持续自优化 + 高阶能力 (持续)

| 步骤 | 任务 |
|------|------|
| 4.1 | 策略自优化 Agent (持续监控 + 提案生成) |
| 4.2 | 每日自动化调度 (Scheduled Runner) |
| 4.3 | Finding 类型扩展 (结构化 Finding UI) |
| 4.4 | Alpha 因子自动挖掘 (AutoFactor + 遗传编程) |
| 4.5 | 策略蒸馏 (好 Agent 决策 → 轻量模型) |

---

## 8. 7 个方向评估总结

| 方向 | 评级 | 在 Ditto 中的位置 |
|------|:----:|-----------------|
| 1. K 线图像/模式识别 | ⭐⭐⭐⭐ | Phase 3: detect_patterns Tool → Instrument Hub Chart View 增强 |
| 2. 裸 K 线基础模型 | ⭐⭐ | 远期: 用 Kronos/TimesFM 预训练权重做微调，不自己训基座 |
| 3. 模仿学习/行为克隆 | ⭐⭐⭐ | Phase 4: 策略蒸馏，将 Agent 好决策固化为轻量模型 |
| 4. 强化学习 | ⭐⭐ | 远期: Agent 执行优化子模块 (智能拆单) |
| 5. 微观结构/订单簿 | ⭐⭐⭐ | 远期: 接入 Level 2 数据后建设 |
| 6. 端到端多模态/Agent | ⭐⭐⭐⭐⭐ | **Phase 1-2 核心**: Agent 团队 + Copilot，直接对接已有数据管线 |
| 7. 自我迭代 Alpha 挖掘 | ⭐⭐⭐⭐ | Phase 3-4: Alpha Explorer + AutoResearch |

---

## 9. 关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 幻觉导致错误因子/策略 | 财务损失 | 所有 Agent 输出必须经过回测验证 + 人工审批；不自动执行 |
| Agent token 成本过高 | 运营成本 | AutoResearch 模式设置实验预算上限；Copilot 模式用缓存减少重复调用 |
| 因子挖掘找到的是过拟合 | 策略失效 | 样本外验证必须通过；Walk-forward 测试；自动过拟合检测 |
| Agent 决策质量不稳定 | 信任下降 | 置信度评分 + 论据链透明化；低置信度 Finding 强制人工审批 |
| 后端 Agent 框架选型错误 | 重写成本 | Phase 1 先用原生 API + 自建编排验证可行性，再考虑引入框架 |

---

## 10. 前端新增/修改页面清单

| 页面/组件 | 类型 | 说明 |
|----------|------|------|
| Alpha Explorer (Research Workspace 内新 tab) | 新增 | 因子挖掘可视化，Copilot + AutoResearch 双模式 |
| AutoResearch Dashboard (Agent Console 增强) | 新增 | 自主研究的结果展示 — 路线图 + 发现清单 + 性能图 |
| Strategy Studio — Guided 模式面板 | 新增 | 左侧对话面板 + Inspector 实时预览联动 |
| Strategy Studio — Agent 模式面板 | 新增 | Agent 活动流 + 策略输出卡片 |
| Strategy Detail — 自优化提案 | 新增 | 策略维护 Agent 的优化提案列表 |
| Agent Console — 结构化 Finding | 修改 | Finding 卡片扩展: 因子候选/策略提案/优化提案/风险预警 |
| Agent Console — Agent 实时活动 | 修改 | Inspector Panel 展示实时活动流 + 工具调用追踪 + 论据链 |
| Copilot Sidecar — 对接真实 SSE | 修改 | 用 Vercel AI SDK useChat 替换 MSW mock |
| Agent Console — 对接真实 API | 修改 | Plans/Runs/Findings 展示真实数据 |
| Home Agent Findings — 结构化展示 | 修改 | Finding 卡片支持因子候选/策略提案等结构化内容 |
