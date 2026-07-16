# Ditto 竞品分析

> 生成日期：2026-04-17 | 模式：--from-existing

---

## 1. 竞品分层

### 1.1 设计参考层

| 产品 | 参考维度 | 借鉴内容 |
|------|---------|---------|
| **Bloomberg Terminal** | 专业终端感 | 锁定视口 + 功能键切换 + 渐进披露 |
| **TradingView** | 图表 + 交互 | 自然滚动 + 可拖拽分栏 + 图表 paneProperties |
| **Koyfin** | 布局模式 | 自然滚动 + 可折叠右面板 |
| **Linear/Vercel/Raycast** | 视觉风格 | 克制感 + 灰阶秩序 + 表面节奏 |
| **Grafana** | 监控仪表盘 | 可配置 widget 面板 |
| **VS Code** | IDE 布局 | 锁定视口 + 可折叠侧栏 + Tab 切换 |

### 1.2 间接竞品层

| 产品 | 定位 | 与 Ditto 关系 |
|------|------|-------------|
| **Wind（万得）** | 金融数据终端 | Ditto 替代目标（数据 + 策略 + 交易一体化） |
| **RiceQuant（米筐）** | 量化研究平台 | 功能重叠（因子/回测），但无实盘闭环 |
| **JoinQuant（聚宽）** | 量化研究平台 | 同上，面向量化入门者 |
| **QMT/PTrade** | 券商交易终端 | Ditto 的交易执行通道（通过 xtquant SDK 集成） |

### 1.3 AI 量化竞品层

| 产品 | Stars | 定位 | 核心用户 | 核心能力 | UI | 实时性 | 多市场 |
|------|-------|------|---------|---------|-----|--------|--------|
| **PandaAI** | 3.5k | 量化因子研究平台 | 量化入门者/散户 | 因子引擎 + 可视化工作流 + ML 训练 | 传统 Web 后台 | 无（批处理） | A 股 |
| **TradingAgents** | AAAI'25 | 多 Agent LLM 交易框架 | AI 研究人员 | 多 Agent 协作 + 多空辩论 | CLI | 无（批处理） | 美股 |
| **daily_stock_analysis** | 30k | AI 股票分析助手 | 个人投资者 | AI 决策仪表盘 + 多渠道推送 + Regime Strategy | 基础 Web | 批处理 | A/港/美 |
| **qlib** | 40.8k | AI 驱动量化投资平台 | ML 工程师/研究员 | SOTA 模型 + RD-Agent + 完整 ML 流水线 | 无（Python） | 无 | 中/美 |
| **OpenBB** | — | 金融数据基础设施 | 金融分析师 | 150+ 数据源 + MCP Server + 多端消费 | Web/CLI/Excel | 无 | 全球 |
| **nautilus_trader** | — | 高性能交易引擎 | 算法交易开发者 | Rust 核心 + 确定性事件驱动 + 纳秒回测 | 无（Python） | 纳秒级 | 15+ 交易所 |
| **Ditto** | 内部 | 专业量化工作站 | 全栈个人量化交易者 | 全链路闭环 + 高密度 UI + Agent 驱动 | 专业工作站 | 实时 | 多市场（A 股核心 + 大宗/贵金属/外汇/指数，后续美股/加密） |

---

## 2. 定位象限

```
                    专业度高
                       │
    nautilus_trader    │    Ditto ★
    qlib               │
                       │
    ───────────────────┼──────────────────→ 实时性高
    TradingAgents      │
    PandaAI            │
    daily_stock_analysis│
    OpenBB             │
                       │
                    专业度低
```

**Ditto 占据独特象限**：专业度高 + 实时性高。竞品要么专业但非实时（qlib/nautilus），要么实时但非专业（daily_stock_analysis），要么两者都不满足（PandaAI/TradingAgents）。

---

## 3. 差异化分析

### 3.1 Ditto 核心差异化

| 差异化轴 | Ditto | 竞品最佳 |
|---------|-------|---------|
| 全链路闭环 | 观测→研→交→风→改进，单一平台 | qlib 有研-回测，nautilus 有执行，无端到端闭环 |
| 专业密度 UI | 工作站级，3 密度档，L1/L2/L3 信息层级 | 竞品均为传统 Web/CLI，无专业密度设计 |
| AI Agent 驱动 | 层级式 Agent 团队，持续自动化投研 | qlib RD-Agent 仅有因子挖掘，TradingAgents 无 UI |
| A 股原生 | T+1/涨跌停/停牌内置，非外挂 | 竞品多为美股/多市场通用，A 股规则不完整 |

### 3.2 竞品优势（Ditto 需要追赶的维度）

| 竞品 | 优势 | Ditto 对策 |
|------|------|-----------|
| **qlib** | 20+ SOTA ML 模型、标准化因子体系（Alpha158/360） | 参考因子体系设计，ML 模型可后期集成 |
| **qlib RD-Agent** | LLM 驱动自动化因子挖掘 | Agent Pipeline 中加入因子挖掘 Agent |
| **OpenBB** | 150+ 数据源、MCP Server 架构 | 可插拔数据层 + MCP 数据接口 |
| **nautilus_trader** | Research-to-Live Parity、纳秒回测 | 回测引擎追求一致性（v1.5+） |
| **daily_stock_analysis** | 30k 社区热度、多渠道推送 | 不同定位，不直接竞争 |
| **TradingAgents** | 多空辩论机制、层级式 Agent | 直接借鉴到 Ditto Agent 架构 |

---

## 4. 值得借鉴的设计

| 来源 | 借鉴点 | 优先级 |
|------|--------|--------|
| TradingAgents | 多空辩论机制（Bull/Bear Researcher 对抗式推理） | 高 |
| TradingAgents | 层级式 Agent 角色分工（Analyst→Researcher→Trader→Risk→PM） | 高（已采纳） |
| daily_stock_analysis | Regime Strategy（进攻/均衡/防守市场状态分类） | 中（已有 Regime 概念） |
| PandaAI | 可视化因子工作流（拖拽式策略构建） | 中 |
| OrgAgent | 层级式优于扁平式的实证数据（+18~124% 性能提升） | 高（已采纳） |
| qlib | 标准化因子体系（Alpha158/360）设计思路 | 低（参考） |
| OpenBB | "Connect once, consume everywhere" 数据架构 | 低（参考） |
| nautilus_trader | Research-to-Live Parity 理念 | 低（参考） |
