# Ditto 产品规格

> Ditto Product Criteria
>
> v2.0 — 2026-08-30 产品边界确认版
>
> 定义 Ditto 产品定位、密度分层准则、元素角色规范和间距体系。
> 这是设计 spec 的上游文档——所有页面蓝图和视觉设计必须符合本规格。

---

## 产品定位

**Ditto** = 本地优先的 A 股个股与 ETF 量化决策、Paper Trading 和手工账户管理工作站，品牌 DNA 是 **Linear/Vercel 的克制感 + Bloomberg/quant desk 的专业终端感**。

**用户画像**: 个人全栈量化投资者，每天长时间与数据、研究和组合事实打交道。信息密度就是生产力。

**产品边界**：宏观、A 股核心/行业指数与全球核心市场数据用于解释 A 股环境；核心可决策资产是 A 股个股和 ETF；系统只提供 Paper 模拟与 Manual 实际账户记录，不连接券商下单。

**产品签名**：每个关键判断都应沿“宏观/全球 → A 股市场 → 行业 → 个股 → 策略/信号 → Model/Paper/Manual → 风险/归因”的证据链下钻。Graphite Studio 是视觉基线，证据链是业务识别度来源。

**审美-功能张力**: 克制感（留白/字号/装饰）vs 信息密度（数据量/可扫视性/操作效率）。
这不是二选一，而是**按模块分层融合**。

---

## 模块分层密度准则

> 不同模块在信息架构中的角色不同，密度标准也不同。

### L1: 核心数据区（高密度）

**模块**: Market Cards、Matrix Table、Driver Strip
**定位**: 用户 80% 时间注视的区域，信息必须密集且可扫视
**密度标准**:
- 间距: 模块内 gap ≤ 16px（紧凑但有序）
- 字号: 数据值 ≥ 12px，标签允许 10px 但必须 L ≥ 0.60
- 留白: 不适用 ≥35% 的通用标准，此区域留白 15-25% 即可
- 行高: 紧凑（1.2-1.4），数据行间距 ≤ 4px

### L2: 辅助信息区（中密度）

**模块**: Context Bar、Right Rail（市场脉搏/风险预警/关键事件/推荐下钻）
**定位**: 支撑 L1 的上下文信息，需要快速扫视但不抢焦点
**密度标准**:
- 间距: 模块内 gap ≤ 12px，模块间 16-24px
- 字号: 标题 ≥ 12px，内容 ≥ 10px（L ≥ 0.60）
- 留白: 25-35%

### L3: 交互与装饰区（克制优先）

**模块**: Tab Band、Status Bar、Badges、Shell Chrome
**定位**: 导航和系统状态，审美服从功能
**密度标准**:
- 交互元素（tab/button/link）: **字号 ≥ 12px，高度 ≥ 24px，可点击区域 ≥ 24×24px**
- 装饰元素（badge/dot）: 最小尺寸 16×16px，不小于容器内文字尺寸
- Status Bar: 高度 20-24px，fixed 定位时必须给 body 添加 padding-bottom 补偿
- 留白: 审美优先，30-40%

### L4: 开发标注区（仅原型）

**模块**: Style Label（"Graphite Studio — Cross-Market Overview · v15"）
**定位**: 原型开发标注，不属于产品 UI
**准则**: `pointer-events: none` 且不得与产品 UI 重叠。审查时忽略此元素。

---

## 元素角色 → 字号映射

> 不同语义角色的元素有不同的最小字号要求。这不是"统一最小字号"，
> 而是"让每个角色用合适的字号"。

| 元素角色 | 最小字号 | 说明 | 示例 |
|---------|---------|------|------|
| 页面标题 | 16px (1rem) | 唯一的视觉锚点 | `.header-title` |
| 区块标题 | 12px | 次级导航锚点 | `.matrix-title`, `.drivers-strip-label` |
| **交互入口** | **12px** | **Tab / Button / Link — 必须可扫视可点击** | `.tab-band-tab`, `.market-card`, `.view-detail-link` |
| 数据值 | 12px | 核心数字 | `.market-card-index`, `.matrix-table td` |
| 数据变化 | 12px | 涨跌幅/变化量 | `.market-card-change`, `.driver-item-change` |
| 正文/标签 | 12px | 描述性文字 | `.market-card-judgment`, `.context-bar-value` |
| 辅助标签 | 10px | 仅用于非交互的纯标识 | `.context-bar-label`, `.rail-section-title` |
| 时间戳/元数据 | 10px | 最小信息 | `.header-timestamp`, `.status-bar` |
| Badge 数字 | **与容器匹配** | Badge 高度 ≥ 文字高度 + 4px padding | `.context-bar-badge` ≥ 14px |

**关键规则**:
1. **10px 不允许用于任何交互元素**（tab/button/link/role="button"）
2. **10px 不允许用于需要用户扫视定位的元素**（section title、column header）
3. **10px 仅用于纯辅助信息**（时间戳、分隔符标签、元数据）
4. 任何 10px 元素必须有 L ≥ 0.60（`--text-tertiary` 标准）

---

## 间距梯度准则

> 间距不应该是固定值，而应该反映信息层级——层级跨度越大，间距越大。

### 模块间间距（Section Gap）

| 层级关系 | 间距 | 说明 |
|---------|------|------|
| L1 → L1（cards → matrix） | 24px | 同级主模块，需要清晰分隔但不过度 |
| L1 → L2（matrix → drivers） | 16px | 主模块到辅助模块，间距递减 |
| L2 → L3（drivers → tab-band） | 12px | 辅助到交互，紧凑衔接 |
| Shell chrome 内部 | 按组件规范 | header/context-bar/rail 各自有固定高度 |

### 间距计算公式

```
section_gap = max(12px, 可用高度 × 2.5%)
```

- VP-STANDARD (1536×1080): 可用 ~988px → 24px
- VP-COMPACT (1366x768): 可用 ~676px → 17px → 取 16px（4px 倍数）

**不使用固定 48px gap**。48px 在信息密集型页面中浪费了 14.5% 的可用空间。

---

## AI 叙事定位

Ditto 的 AI 不是独立的"AI 域"，而是**嵌入各业务域的智能层**。

核心叙事（v2.0 嵌入方案）：

- **AI Copilot 是全局 Sidecar 组件**——不属于任何域路由，可从任意页面唤出，提供市场分析、选股辅助、策略草案、因子发现等能力
- **AI Agent Console 归入 System 域**（迁移期路径仍可为 `/platform/agents`）——自主执行研究任务的 Agent 工作台，产出 Finding 经审批后进入 Signals Inbox
- **AI 能力嵌入业务域页面**——因子发现、策略生成、信号解读等 AI 能力不再有独立入口，而是作为各业务域页面的内嵌功能
- **AI 融入工作流，不独立于工作流**——Copilot 的产出可发送到 Strategy Studio / Watchlist / Research；Agent 的 Finding 经审批后直接对接 Signals Inbox

> 详见 [01 产品信息架构 §7.5](01_product_information_architecture.md) 和 [06 核心用户流程 Flow C](06_core_user_flows.md)。

---

## System 域收敛说明

System 域承接原 Platform 的技术路径，但用户可见产品心智统一为 System：

| 迁移期路径 | 承载内容 |
|-----------|---------|
| `/platform` | 平台运维总览：Data Quality + Pipelines/Jobs + System Alerts + Health Strip |
| `/platform/settings` | 集中配置：只读 Data Providers + 通用 Settings；不得出现券商下单配置 |

实时行情数据源是只读 Provider。Broker 不是被折叠的设置项，而是明确排除的产品能力。

## 完成度判定

页面、route、contract、overlay 和原型数量只能证明界面结构存在。产品完成必须由真实数据、freshness/PIT、错误与空态、以及“市场判断 → 选股 → Paper → 实际账户记录 → 复盘”的端到端任务证据共同验收。

> 详见 [01 产品信息架构 §7.6](01_product_information_architecture.md)。

---

## 与其他 spec 的关系

- **上游**: [00_ditto_visual_constitution.md](00_ditto_visual_constitution.md) — 视觉原则（判断 > 操作 > 美感）
- **下游**: [01_product_information_architecture.md](01_product_information_architecture.md) — IA 结构
- **下游**: [02_core_page_blueprints.md](02_core_page_blueprints.md) — 页面蓝图（应用本规格的密度准则）
- **审查引用**: `.claude/design-review/review-scoring.md` — 审查评分时引用本规格中的量化标准
