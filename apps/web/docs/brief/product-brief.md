# Ditto Product Brief

> 逆向生成于现有 spec（00-18），标注置信度：🟢 高 / 🟡 中 / 🔴 低
> 生成日期：2026-04-17 | 模式：--from-existing

---

## §1 Vision

### 1.1 产品定位 🟢

**Ditto 是面向全栈个人量化交易者的多市场量化研究+实盘闭环内部量化平台。**

- 非商业 SaaS，非单点研究工具，非信息展示门户
- 内部量化平台，支持多用户使用
- 当前以 A 股为核心市场，引入部分大宗商品、贵金属、外汇和国际主流指数
- 后续全面扩展：美股、加密货币
- 核心工作流：Observe → Discover → Research → Validate → Execute → Monitor/Improve

### 1.2 用户角色 🟢

**核心用户：全栈个人量化交易者**

一个用户同时承担三类角色，由 AI Agent 团队辅助分担工作量：

| 角色维度 | 职责 | 活跃时段 | AI Agent 辅助 |
|---------|------|---------|-------------|
| **策略研究员** | 因子分析、策略构建、回测验证 | 盘后（15:00-22:00） | 自动化因子挖掘、策略草稿生成 |
| **交易执行者** | 信号复核、下单执行、风控监控 | 交易时段（9:15-15:00） | 信号预筛选、执行建议 |
| **系统维护者** | 数据质量监控、配置管理 | 非交易时段 | 数据异常自动告警 |

**AI Agent 团队**（层级式架构，参考 TradingAgents + OrgAgent）：

| Agent 层级 | 角色 | 职责 |
|-----------|------|------|
| 分析师团队 | 基本面/技术面/情绪面/新闻面分析师 | 多维度数据分析 |
| 研究员团队 | 多头研究员/空头研究员 | 对抗式辩论推理 |
| 交易员 | 交易 Agent | 综合研判，交易决策 |
| 风控经理 | 风控 Agent | 波动率/流动性/集中度评估 |
| 组合经理 | PM Agent | 最终审批/拒绝交易提案 |

### 1.3 核心痛点 🟢

| # | 痛点 | 现状 |
|---|------|------|
| P1 | 工具碎片化 | Wind 看数据、Python 写策略、券商客户端下单，切换成本高 |
| P2 | 研-交链路断裂 | 信号复核到下单之间信息丢失，风控与研-交割裂 |
| P3 | 因子衰减难追踪 | 因子性能衰减缺乏实时监测，衰减→策略更新闭环缺失 |
| P4 | 风控被动滞后 | 风险异常事后发现，缺少主动预警和风控→策略调整回路 |

### 1.4 差异化价值 🟢

| 轴 | 差异化 | vs 竞品 |
|----|--------|---------|
| **闭环** | 观测-研-交-风全链路闭环 | vs 竞品的单点工具定位 |
| **密度** | 专业工作站级 UI，高密度信息呈现 | vs 竞品的传统 Web 后台/CLI |
| **AI** | AI 工作流加速器，Agent 驱动自动化投研 | vs 竞品的 AI 辅助/无 AI |
| **自动化** | Agent 可驱动的持续投研、持续回测、持续策略挖掘验证 | vs 竞品的批处理/手动触发 |

### 1.5 成功标准 🟢

**定性标准：**
- 快速态势感知：用户进入任意页面 5 秒内回答关键问题
- 持续闭环：研-交-风链路零断裂点
- 可持续高密度：3 小时连续使用不疲劳，30 天持续使用仍可信
- Agent 可驱动：持续投研、持续回测、持续特征策略挖掘验证的自动化工作流

---

## §2 System 摘要

### 2.1 领域模型 🟢

18 个核心实体，详见 `system-description.md`：

**市场层**：Instrument、Universe、Regime
**研究层**：Research、Factor、Feature、Strategy、Experiment
**验证层**：Backtest
**交易层**：Signal、Order、Execution、Account
**风控层**：Risk、Portfolio
**AI 层**：AgentPlan、AgentFinding、Pipeline

### 2.2 能力域 🟢

6 大能力域，30+ 细分能力，详见 `system-description.md`：

- 市场观测与发现
- 标的分析
- 因子研究与策略构建
- 交易执行与风控
- AI Agent 协同
- 平台运维

### 2.3 数据架构 🟢

可插拔数据源架构，当前 4 个适配器：tushare（历史）、MiniQMT（实时+交易）、通达信（辅助）、FRED（宏观）。数据层独立解耦，支持未来扩展。

---

## §3 Constraints 摘要

详见 `constitution.md`。核心约束：

- **技术约束**：当前技术栈（React 19/FastAPI/Zustand/TanStack Query）确定性较高，变更需详细评估
- **产品边界**：非 SaaS、非 Chat UI、非卡片墙、非 SEO 内容产品
- **UX 原则**：长期可用性优先、专业感来自控制、市场色规范、AI 审批门控
- **美学标准**：独特品味，脱离 AI coding 廉价 UI 感，合理突破尝试

---

## §4 Research Index

- 竞品分析：`docs/research/competitive/landscape.md`
- 领域知识缺口：`docs/research/domain/knowledge-gaps.md`

---

## §5 Assumption Summary

共识别 6 个需验证假设（3 High + 3 Medium），详见 `assumptions.md`。

| 风险 | 假设 | 状态 |
|------|------|------|
| 🔴 High | Agent 决策质量——层级式 Agent 能产生可执行决策而非噪声 | unvalidated |
| 🔴 High | LLM 金融分析准确性——非幻觉，足以支持交易决策 | unvalidated |
| 🔴 High | 数据源可靠性——tushare/MiniQMT 满足实时交易需求 | unvalidated |
| 🟡 Medium | 高密度 UI 可持续性——长时间使用不导致认知过载 | unvalidated |
| 🟡 Medium | 因子衰减闭环可行性——检测→策略调整回路实际可运行 | unvalidated |
| 🟡 Medium | 实时连接稳定性——WebSocket 在市场高峰期保持稳定 | unvalidated |
