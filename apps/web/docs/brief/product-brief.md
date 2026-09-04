# Ditto Product Brief

> 初版逆向生成于现有 spec（00-18）
> 生成日期：2026-04-17 | 产品边界复核：2026-08-30
> 状态：已按 D1—D10 确认；与旧 spec 冲突时，以后端确认版[产品基线报告](../../../ditto/docs/reviews/2026-08-30-system-product-positioning-and-app-blueprint-baseline.md)为准

---

## §1 Vision

### 1.1 产品定位 🟢

**Ditto 是面向个人全栈量化投资者的本地优先 A 股量化决策与组合管理工作站。**

- 非商业 SaaS，非单点研究工具，非信息展示门户
- 默认单用户、本地运行
- A 股个股与 A 股 ETF 是核心可决策资产，选股与行业轮动是一级主流程
- A 股核心/行业指数、全球核心指数、利率、汇率、商品与宏观数据用于环境和风险解释，不扩展为全球交易
- 不连接 A 股券商，不提交、修改或撤销真实订单；实时数据接入保持只读
- 核心工作流：Observe → Discover → Research → Validate → Decide → Record → Review/Improve

### 1.2 用户角色 🟢

**核心用户：全栈个人量化交易者**

一个用户同时承担三类角色，由 AI Agent 团队辅助分担工作量：

| 角色维度 | 职责 | 活跃时段 | AI Agent 辅助 |
|---------|------|---------|-------------|
| **策略研究员** | 因子分析、策略构建、回测验证 | 盘后（15:00-22:00） | 自动化因子挖掘、策略草稿生成 |
| **组合管理者** | 信号复核、目标仓位、Paper、手工账户、风控与复盘 | 交易时段（9:15-15:00）及盘后 | 信号预筛选、组合解释 |
| **系统维护者** | 数据质量监控、配置管理 | 非交易时段 | 数据异常自动告警 |

**AI Agent 团队**（层级式架构，参考 TradingAgents + OrgAgent）：

| Agent 层级 | 角色 | 职责 |
|-----------|------|------|
| 分析师团队 | 基本面/技术面/情绪面/新闻面分析师 | 多维度数据分析 |
| 研究员团队 | 多头研究员/空头研究员 | 对抗式辩论推理 |
| 决策助手 | Decision Agent | 综合研判，形成候选与组合建议 |
| 风控经理 | 风控 Agent | 波动率/流动性/集中度评估 |
| 组合经理 | PM Agent | 最终审批/拒绝交易提案 |

### 1.3 核心痛点 🟢

| # | 痛点 | 现状 |
|---|------|------|
| P1 | 工具碎片化 | 数据、研究、选股、Paper、实际账户记录和复盘分散 |
| P2 | 市场到组合链路断裂 | 宏观/行业判断、个股选择、信号、目标仓位和实际持仓之间缺少证据链 |
| P3 | 因子衰减难追踪 | 因子性能衰减缺乏实时监测，衰减→策略更新闭环缺失 |
| P4 | 账户事实不完整 | Paper 不能持续运行，实际账户缺少独立、可更正、可重建的手工账本 |

### 1.4 差异化价值 🟢

| 轴 | 差异化 | vs 竞品 |
|----|--------|---------|
| **闭环** | 环境-行业-选股-研究-组合-账户-复盘全链路 | vs 竞品的单点工具定位 |
| **密度** | 专业工作站级 UI，高密度信息呈现 | vs 竞品的传统 Web 后台/CLI |
| **AI** | AI 工作流加速器，Agent 驱动自动化投研 | vs 竞品的 AI 辅助/无 AI |
| **自动化** | Agent 可驱动的持续投研、持续回测、持续策略挖掘验证 | vs 竞品的批处理/手动触发 |

### 1.5 成功标准 🟢

**定性标准：**
- 快速态势感知：用户进入任意页面 5 秒内回答关键问题
- 持续闭环：市场判断、选股、Paper、实际账户记录和复盘链路零断裂点
- 可持续高密度：3 小时连续使用不疲劳，30 天持续使用仍可信
- Agent 可驱动：持续投研、持续回测、持续特征策略挖掘验证的自动化工作流
- 真实可用：完成度由真实数据、新鲜度/PIT 证据和端到端用户任务决定，不由路由或原型数量决定

---

## §2 System 摘要

### 2.1 领域模型 🟢

核心实体详见 `system-description.md`；必须明确区分市场参照、可决策资产和三类组合事实：

**市场层**：A 股 Instrument、Universe、Industry、Regime，以及不可交易的 Macro/Market Reference
**研究层**：Research、Factor、Feature、Strategy、Experiment
**验证层**：Backtest
**组合层**：Signal、Model Portfolio、Paper Order/Fill、Manual Account Event、Account
**风控层**：Risk、Portfolio View
**AI 层**：AgentPlan、AgentFinding、Pipeline

### 2.2 能力域 🟢

五个用户可见产品域，详见产品信息架构：

- Today：当天判断、优先事项和异常
- Markets：宏观、全球/A 股市场、行业强弱、筛选和标的分析
- Research：因子、策略、回测、实验和标的池
- Portfolio：Model、Paper、我的账户、风险、归因和复盘
- System：数据、任务、配置、Agent 和审计

AI 是嵌入五域的能力层，不是独立产品域。

### 2.3 数据架构 🟢

数据层保持可插拔与只读接入。已存在 tushare、通达信和 FRED 等能力，但数据集覆盖、许可、发布时间、修订版本、时区、新鲜度和真实消费链必须逐项验证。MiniQMT 不再是产品依赖，也不得作为交易通道；实时行情 provider 在后续数据方案中单独验证。

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

当前优先验证以下产品假设；这张表不宣称能力已经可用：

| 风险 | 假设 | 状态 |
|------|------|------|
| 🔴 High | Agent 决策质量——层级式 Agent 能产生可执行决策而非噪声 | unvalidated |
| 🔴 High | LLM 金融分析准确性——非幻觉，足以支持投资判断与候选解释 | unvalidated |
| 🔴 High | 宏观、全球核心指数与实时行情的数据源在个人使用范围内具备许可、稳定性、PIT 与新鲜度 | unvalidated |
| 🔴 High | Paper 可连续运行、恢复并与同周期回测解释一致 | unvalidated |
| 🔴 High | Manual 账户能以独立事件完整重建现金、持仓、费用、税费和收益 | unvalidated |
| 🟡 Medium | 高密度 UI 可持续性——长时间使用不导致认知过载 | unvalidated |
| 🟡 Medium | 因子衰减闭环可行性——检测→策略调整回路实际可运行 | unvalidated |
| 🟡 Medium | 行业强弱与个股选择证据能显著改善每日候选形成效率 | unvalidated |
