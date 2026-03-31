# 产品架构审计修复 — 关键决策

**日期**: 2026-03-31
**来源**: /ditto-product-arch --audit（审计发现 29 个问题）
**状态**: 已采纳

---

## 1. /ai 总览页 Pattern 归属决策

- **选择**: `/ai` 采用 **Global Command Center 的轻量变体**
- **淘汰**: Object Hub（10 Shell 提议）、Analytical Overview Workspace（11 Pattern 残留）
- **Why**: /ai 的核心动词是"感知 + 分流"（了解 AI 最近做了什么、哪些需要处理、去哪个工作台），与 Home 的"orient"模式一致。/ai 不围绕单一对象展开（非 Object Hub），也不承载深度分析（非 Analytical）
- **How to apply**: 01 IA §7.5 新增 Pattern 决策说明，11 Pattern §12.5 映射表修正
- **同步文档**: 01 IA、10 Shell、11 Pattern

---

## 2. Context Transfer Protocol 设计决策

- **选择**: 采用 URL 参数协议 `?ctx[key]=value` 传递跨域上下文
- **Why**: 轻量、无状态、向后兼容。目标页面支持无参数直接访问，参数仅用于初始化状态
- **How to apply**: 06 核心用户流程 §8 定义协议格式和 6 条已定义跨域路径
- **已定义路径**:
  1. Instrument Hub → Research（携带 instrument ID，自动筛选关联因子）
  2. Copilot → Strategy Studio（携带 AI 草案，加载到 Code Mode）
  3. Backtest → Copilot（携带回测上下文，Strategy Draft 模式解读）
  4. Screener → Strategy Studio（批量导入标的）
  5. Risk Center → Strategy Studio（定位到风控参数面板）
  6. Agent Finding → Signals（自动创建并筛选信号）

---

## 3. A 股交易规则 UI 落地方案

- **选择**: A 股交易规则不创建独立页面，嵌入现有页面
- **嵌入位置**:

| A 股特性 | 嵌入位置 |
|---------|---------|
| T+1 冻结标识 | Trading Overview Positions Summary 列 |
| 涨跌停校验 | Signals Inbox 信号表 + Scope Strip |
| 交易阶段指示 | Trading Overview Session Strip |
| 龙虎榜 | A 股总览 Bottom Tab Band |
| 两融数据 | A 股总览 Bottom Tab Band + Trading Session Strip |
| 北向资金深度 | A 股总览 Right Rail |
| 停牌/复牌 | Instrument Hub Object Header + Meta Strip |
| 最小交易单位 | Orders 页面（100 股约束） |
| 交易成本明细 | Backtest Result Bottom Area |

- **Why**: 遵循"不新增独立路由"的克制原则，A 股特性作为上下文嵌入现有页面。用户在需要时自然看到，不需要时不会增加噪声
- **同步文档**: 02 蓝图 §2.1/§4/§8/§9/§10

---

## 4. Platform 域收敛决策

- **选择**: v1 Platform 域从 6 个路由收敛为 2 个核心路由
- **v1 结构**:

| 路由 | 承载内容 |
|------|---------|
| `/platform` | 平台运维总览（Data Quality + Pipelines/Jobs + Alerts + Health Strip） |
| `/platform/settings` | 集中配置（Data Providers + Brokers + Settings） |

- **Why**: v1 用户通常只有 1 个数据源和 1 个券商，独立管理页面 ROI 过低。收敛为 settings Tab 视图更符合"个人量化工作台"定位
- **扩展路径**: v2 若接入 3+ 数据源/券商时，可拆分为独立路由
- **同步文档**: 00 产品规格、01 IA §7.6

---

## 5. Improve 回路（Flow D）定义决策

- **选择**: 新增 Flow D 作为独立于 Flow B 的"维护性工作流"
- **Why**: 核心链路声称"Monitor/Improve"，但 Monitor 到 Improve 缺乏显式路径。长期使用用户会频繁走这条回路
- **How to apply**: 06 核心用户流程新增 §3.5，定义 detect → diagnose → adjust → revalidate → update 五步回路
- **关键设计**: Flow D 的起点和验证点都是 Risk Center，终点是 Signals Inbox（与 B/C 终点一致）
