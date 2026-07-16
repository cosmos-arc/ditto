# Ditto 产品架构审计报告

> **审计日期**: 2026-03-31
> **审计模式**: `--audit`（四角色并行）
> **审计范围**: 全部 spec 文档 (00-15) + 设计决策 + 原型

---

## 审计范围

| 文档 | 版本/状态 | 说明 |
|------|----------|------|
| 00 视觉宪章 | v1.0 Final | 8 条最高层原则 |
| 00 产品规格 | v1.0 | 密度分层、字号映射、间距梯度 |
| 01 产品信息架构 | v1.0 | 6 域 Sitemap、8 套页面模式、3 批次优先级 |
| 02 核心页面蓝图 | v1.0 Final | 15 个核心页面（含 wireframe） |
| 03 对象页统一规范 | v1.0 Final | 统一骨架、Header/Meta/Tab/Panel 规范 |
| 04 交互与状态规范 | v1.0 Final | 15 种状态语义、5 级反馈 |
| 10 Shell Family | v1.0 Final | 6 类 Shell + Radar 子变体 |
| 11 Page Pattern Library | v1.0 Final | 8 套页面模式 |
| 12 Data Views | v1.0 Final | Table/Context/Visual 三族 + 联动 |
| 13 Component Spec | v1.0 Final | 7 大组件组 + AI/Agent + Cross-Market |
| 14 Token Naming | v1.0 Final | 9 层 Token 体系 |
| 15 Token Stabilization | v1.3 Active | 9/9 层落地，评分 78/100 |
| 设计决策 | 2026-03-28~30 | Style B、字体、密度、OKLCH、涨跌色等 9 项 + Home/CC 分家 + 色彩语义 |

---

## 综合评分

### 五维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **IA 覆盖度** | 8/10 | 15 页蓝图覆盖核心链路，6 域结构稳定。扣分：三文档映射表 15+ 处路由不一致 |
| **标签一致性** | 6/10 | 中英文标签跨文档有 10+ 处不一致，缺少统一术语表 |
| **导航可达性** | 8/10 | 全站 ≤ 3 层，未发现孤立页面。扣分：部分降级路由在 Shell/Pattern 中仍存在 |
| **流程完整性** | 7/10 | 6 环节工作流覆盖充分。扣分：Backtest→Signal→Order 闭环有断裂点；无独立用户流程文档 |
| **文档同步度** | 6/10 | IA 收敛决策未同步到 Shell/Pattern 映射表；Home/CC 分家未回写 IA |

### 总评

| 综合得分 | 等级 |
|---------|------|
| **7.0 / 10** | **良好但有系统性同步债务** |

---

## 发现的问题

### P0: 结构性问题（4 项）

#### P0-1: 三文档映射表严重不同步

**影响**: 设计者或开发者以 Shell/Pattern 映射表为参考，会实现出与 IA 决策矛盾的路由结构。

IA 文档做出了 8 项收敛决策（§6.1-§6.8），但 Shell Family 和 Pattern Library 的映射表未跟进。

**具体差异**:

| 类别 | 差异路由数 | 典型示例 |
|------|----------|---------|
| IA 已降级但 Shell/Pattern 仍保留 | 5 | `/home/pending`, `/home/quick-actions`, `/home/alerts-summary`, `/markets/map`, `/research/ml` |
| IA 已合并但 Shell/Pattern 仍分离 | 5 | AI 域 3 路由→合并为 copilot 模式；Strategy new/editor→合并为 studio |
| IA 无但 Shell/Pattern 有 | 12 | `/research/output`, `/trading/accounts`, `/trading/portfolios`, `/trading/risk/stress-test` 等 |
| Shell vs Pattern 分类矛盾 | 4 | `/markets/screener`, `/trading/accounts`, `/platform/accounts`, `/platform` 命名 |
| 路由名不一致 | 3 | `/trading/risk` vs `/trading/risk/dashboard`；`/factors/[id]` vs `/factors/[id]/analysis` |

**建议修复**: 以 IA Sitemap 为权威源，同步更新 Shell Family §10 和 Pattern Library §12 的映射表。

#### P0-2: Home vs Command Center 分家决策未同步到 IA 文档

**影响**: IA §7.1 仍将 Home 定义为 "Command Center"，与分家决策（Home=orient, CC=execute）矛盾。

**涉及文件**: `01_product_information_architecture.md` §7.1

**建议修复**: 更新 IA §7.1 的 Home 角色定义，明确 Home 的核心动词是 orient（定向/分流），不是 execute（执行）。同步更新 Sitemap 中的 Home 路由描述。

#### P0-3: 缺少独立用户流程文档

**影响**: 三条核心 happy path 存在断裂点：
- **Backtest→Signal→Order**: Strategy Studio 提交回测后，回测结果如何转为信号、信号如何转订单的路径在蓝图中不连贯
- **AI 审批→执行**: Agent Console 的 approval 状态如何连接到 Trading 域的执行队列未定义
- **Market 发现→Research**: 从 Market Card 跳转到 Instrument Hub 后，如何进入研究工作流未明确

**涉及文件**: 当前无独立流程文档，散布在 IA §3 和 Blueprint 的"主要跳转"中。

**建议修复**: 创建 `docs/designs/specs/06_core_user_flows.md`，至少覆盖 3 条核心 happy path + 错误分支。

#### P0-4: 缺少统一术语表

**影响**: 16 份 spec 文件中散布着中英文金融术语，存在 10+ 处不一致：
- "Breadth" vs "涨跌比" vs "广度" vs "偏强"
- "Movers" vs "涨跌幅排名" vs "Main Theme Activity"
- "北向" vs "北向资金" vs "北向流入" vs "北向净流入"
- "Operations Console" vs "Ops Console" vs "运维控制台"

**建议修复**: 创建 `docs/designs/specs/16_ditto_glossary.md`。

---

### P1: 一致性问题（7 项）

#### P1-1: `/markets/screener` 分类矛盾

| 文档 | 分类 |
|------|------|
| IA §8.3 | Catalog / Screener Workspace |
| Shell §10.2 | Analytical Workspace |
| Pattern §12.2 | Catalog / Screener Workspace |

Screener 确实有分析特征（比较、评分），需产品决策统一。

#### P1-2: `/trading/accounts` 分类矛盾

| 文档 | 分类 |
|------|------|
| Shell §10.4 | Catalog Workspace |
| Pattern §10.2 | Ledger / Execution Console |

#### P1-3: `/platform/accounts` 分类矛盾

| 文档 | 分类 |
|------|------|
| Shell §10.6 | Operations Console |
| Pattern §12.6 | Config / Integration Console |

#### P1-4: Risk Center 路由名不一致

IA: `/trading/risk`，Shell/Pattern: `/trading/risk/dashboard`。

#### P1-5: Factor 对象页路由后缀不一致

IA: `/research/factors/[id]`，Shell/Pattern: `/research/factors/[id]/analysis`。

#### P1-6: A 股交易约束未在 Trading 域体现

T+1 交收、涨跌停限制、ST 标的约束等核心规则在 Trading Overview、Signals Inbox、Orders Ledger 中均未提及。

#### P1-7: 回测指标体系不够完整

Backtest KPI Strip 缺少 Sortino、Calmar、Skewness、Kurtosis、Alpha/Beta 等业界标准指标。

---

### P2: 优化建议（8 项）

| # | 建议 | 预期收益 |
|---|------|---------|
| P2-1 | 建立路由注册表（Route Registry），所有文档从注册表派生 | 消除映射不同步的根因 |
| P2-2 | 统一 Shell/Pattern "页面角色"命名（Operations Console vs Queue/Ops Console） | 降低理解成本 |
| P2-3 | 为 `/ai` 总览页明确 Shell 类型（Shell 留两种可能，Pattern 已选 Object Hub） | 消除歧义 |
| P2-4 | Intelligence 路由收敛需在映射表中明确为单一路由（非通配符） | 实现清晰 |
| P2-5 | Instrument Hub 增加"股东/机构"维度或 Tab | A 股投资者核心需求 |
| P2-6 | A 股 Context Bar 增加"两市成交额"和"涨跌停家数" | 核心量能指标 |
| P2-7 | Scope Strip 数据支撑化（附板块强度数据而非纯文字） | 可信度 |
| P2-8 | Risk Center 增加 A 股特有风险维度（行业集中度/风格暴露/流动性） | 本地化深度 |

---

## 四角色审计摘要

### Product Strategist（产品策略师）— 7.2/10

| 维度 | 评分 |
|------|------|
| 产品定位清晰度 | 8 |
| 用户画像具体性 | 5 |
| 核心工作流匹配 | 9 |
| 功能边界合理性 | 8 |
| 竞品差异化 | 6 |
| 市场优先级 | 7 |

**核心发现**: 用户画像仅一句话（"专业交易员/投资者，每天 8+ 小时"），缺乏行为模式、痛点、技术水平假设。缺乏系统性竞品分析文档。

### Information Architect（信息架构师）— 7.5/10

| 维度 | 评分 |
|------|------|
| 导航模型一致性 | 7 |
| 页面层级深度 | 9 |
| 内容分组逻辑 | 8 |
| 导航可达性 | 8 |
| 标签体系一致性 | 6 |
| 页面间关系 | 7 |
| 增量扩展性 | 9 |
| 文档间映射一致性 | 6 |

**核心发现**: IA→Shell→Pattern 三文档映射表存在 15+ 处路由差异，是最突出的系统性问题。六域骨架和扩展点预留良好。

### UX Strategist（UX 策略师）— 6.9/10

| 维度 | 评分 |
|------|------|
| Happy Path 完整性 | 7 |
| 错误分支覆盖 | 6 |
| 入口/出口设计 | 8 |
| 交互模式选择 | 8 |
| 渐进展示策略 | 7 |
| 认知负荷控制 | 7 |
| 死端检测 | 7 |
| 跨页面流程 | 6 |
| 用户流程文档完整性 | 4 |

**核心发现**: 缺少独立用户流程文档。Backtest→Signal→Order 闭环有断裂。AI 审批后执行路径未定义。

### Domain Expert（金融领域专家）— 6.75/10

| 维度 | 评分 |
|------|------|
| 资产分类合理性 | 7 |
| A 股市场规则体现 | 6 |
| 量化工作流覆盖 | 8 |
| 数据类型正确性 | 7 |
| 术语准确性 | 8 |
| 术语表完整性 | 3 |
| 竞品对标专业性 | 7 |
| 时效性数据设计 | 8 |

**核心发现**: 量化因子研究链路专业且完整。A 股交易约束（T+1/涨跌停/ST）未在 Trading 域设计中体现。缺少统一术语表。回测指标缺少高级指标。

---

## 待同步清单

- [x] **同步 IA→Shell 映射表**: IA Sitemap §5 的收敛决策需回写到 Shell §10 映射表（~20 个路由差异）→ **2026-03-31 已同步**
- [x] **同步 IA→Pattern 映射表**: 同上，回写到 Pattern §12 映射表（~18 个路由差异）→ **2026-03-31 已同步**
- [x] **回写 Home/CC 分家决策**: 更新 IA §7.1 Home 角色定义 → **2026-03-31 已更新**
- [x] **裁决 Screener 分类**: IA/Pattern vs Shell 的矛盾需产品决策 → **已裁决为 Catalog/Screener（业界 5/5 平台均归类为发现工具）**
- [x] **裁决 Trading Accounts 分类**: Shell vs Pattern 的矛盾需产品决策 → **已裁决为 Trading=Catalog, Platform=Config（业界 7/7 平台均为浏览选择型）**
- [x] **统一 Risk Center 路由**: `/trading/risk` vs `/trading/risk/dashboard` → **已统一为 `/trading/risk`**
- [x] **统一 Factor 对象页路由**: `/factors/[id]` vs `/factors/[id]/analysis` → **已统一为 `/research/factors/[id]`**
- [x] **创建术语表**: `16_ditto_glossary.md` → **2026-03-31 已创建 v2.0（14 类 130+ 术语）**
- [x] **创建用户流程文档**: `06_core_user_flows.md` → **2026-03-31 已创建 v1.0（3 条核心流程 + 6 个断裂点）**
- [ ] **补充 A 股交易规则**: Trading 域蓝图增加 T+1/涨跌停/ST 约束

---

## 亮点（值得保持）

1. **9 层 Token 体系**: 从 Foundation 到 Module Pattern 的分层在业界量化平台中领先
2. **7 域 Domain Semantic**: 颜色按业务域分离（market/risk/execution/system/data-quality/model/agent），避免了金融终端常见的颜色语义混淆
3. **Radar Shell 子变体**: 双层 Context（Context Bar + Scope Strip）设计创新
4. **收敛纪律**: IA 文档主动收敛了 8 项旧思路，体现了产品克制
5. **壳层反模式清单**: Shell §13 的 10 项反模式检查表对实现有直接指导价值
6. **涨跌色数值语义**: 坚持正=涨色/负=跌色，CN/Intl 双模式，token 三层一致
7. **Data freshness 三级体系**: live/stale/expired 配合交互规范，解决了量化平台最常见的数据时效性问题
8. **AI 组件角色化**: Conversation Block / Research Note / Tool Invocation Row 等避免了"聊天产品化"
