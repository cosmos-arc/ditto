# Markets > 全市场总览（Cross-Market Overview）设计文档

> **版本**：v1.0
> **日期**：2026-03-29
> **状态**：Draft — 待验证
> **上游**：[01 产品信息架构](../designs/specs/01_product_information_architecture.md)、[02 核心页面蓝图](../designs/specs/02_core_page_blueprints.md)、[10 Shell Family](../designs/specs/10_ditto_shell_family_spec.md)、[11 Page Pattern Library](../designs/specs/11_ditto_page_pattern_library.md)
> **下游**：前端组件实现、路由配置、Shell 变体实现

---

## 1. 页面定位

### 1.1 核心动词

**scan → compare → choose where to drill down**

这张页是"跨市场雷达页"，不是"大而全数据堆叠页"，不是 quote board。

### 1.2 回答的 5 个问题

1. 今天全球总体是 Risk-On 还是 Risk-Off
2. 哪些市场 / 资产类别最强，哪些最弱
3. 驱动当前市场分化的核心变量是什么
4. 哪些市场值得我点进去继续看
5. 接下来 24 小时有什么重要事件会改变格局

### 1.3 页面角色边界

**应该做：**
- 展示全球多市场的整体 regime
- 让用户快速比较 A 股、港股、美股、利率、外汇、黄金、原油等主要市场
- 提供跨市场的相对强弱、波动、资金偏好、事件风险线索
- 引导用户下钻到单市场页

**不应该做：**
- 深入单市场行业结构
- 展示过多单资产明细
- 提供执行、下单、复核类动作
- 变成 Home 的替代页
- 变成全球行情软件式 quote board

### 1.4 页面语言策略

| 允许出现 | 禁止出现 |
|---------|---------|
| 进入 A 股总览 | 执行 |
| 查看港股 | 复核 |
| 打开商品页 | 下单 |
| 查看事件详情 | 交易 |
| 固定视角 | |
| 加入观察 | |

---

## 2. 信息架构更新

### 2.1 Markets 域路由重构

将 Markets 从"其实是 A 股页"重构为完整域。

```
Markets 域（重构后）
├── /markets              → 全市场总览（Cross-Market Overview）← 新页面
├── /markets/a-shares     → 中国 A 股总览 ← 从原 /markets 迁入
├── /markets/hk           → 港股总览（v1.5）
├── /markets/us           → 美股总览（v2）
├── /markets/fx           → 外汇总览（v2）
├── /markets/rates        → 利率总览（v2）
├── /markets/commodities  → 商品总览（v2）
├── /markets/screener     → 不变
├── /markets/universes    → 不变
├── /markets/watchlist    → 不变
├── /markets/intelligence → 不变
├── /markets/chart-lab    → 不变
├── /markets/calendar     → 不变
└── /instruments/[id]     → 不变
```

### 2.2 迁移策略

- `/markets` 指向新的全市场总览
- 现有 A 股结构页原型迁至 `/markets/a-shares`
- 子路由 `/markets/screener` 等不受影响
- 如存在旧书签/外链，做兼容跳转

### 2.3 页面分工体系

| 页面 | 核心动词 | 关键词 | 说明 |
|------|---------|--------|------|
| Home | orient | 理解 → 分流 | 全域状态与今天去哪 |
| **全市场总览** | **scan / compare** | **扫 → 比 → 选** | 跨市场 regime、强弱、驱动、事件 |
| 中国 A 股总览 | structure scan | 结构扫描 | A 股内部结构、行业、宽度、北向 |
| 港股总览 | structure scan | 结构扫描 | 港股内部结构、科技、南向 |
| Command Center | execute | 判断 → 执行 | 今天该做什么、先做什么 |

### 2.4 需同步更新的文档

| 文档 | 变更内容 |
|------|---------|
| `01_product_information_architecture.md` §5 | Sitemap 新增 `/markets/a-shares` |
| `02_core_page_blueprints.md` §2 | 重写为全市场总览；新增 A 股总览条目 |
| `10_ditto_shell_family_spec.md` §4.2 | Analytical Shell 新增 Radar 子变体 |
| `11_ditto_page_pattern_library.md` §5 | 新增 Pattern 02-C Market Radar Workspace |
| `13_ditto_component_spec.md` | 新增 Market Card、Macro Driver Block 等组件定义 |

---

## 3. Shell 定义：Analytical / Radar 子变体

### 3.1 定位

这不是第 7 个独立 Shell，而是挂在 Analytical Workspace Shell 下的子变体。

内部命名：**Analytical Shell / Radar Variant**

### 3.2 适用页面

- `/markets` — 全市场总览
- `/markets/a-shares` — 中国 A 股总览
- `/markets/hk` — 港股总览
- `/markets/us` — 美股总览
- 后续 `/markets/fx`、`/markets/rates`、`/markets/commodities`

### 3.3 核心骨架

```
┌ Rail ┬───────────────────────────────────────────────────────────────┐
│      │ Workspace Header（标题 + 时间框架 + 刷新时间 + 视图密度）        │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Context Bar（全局环境条 — 客观变量）                             │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Scope Strip（今日解读条 — 人话摘要）                             │
│      ├───────────────────────────────────┬───────────────────────────┤
│      │ Main Stage (70%)                  │ Right Rail (30%)          │
│      │                                   │                           │
│      │ ┌─────────┬─────────┬─────────┐   │ 市场脉搏摘要               │
│      │ │ Card 1  │ Card 2  │ Card 3  │   │ ─────────────────────── │
│      │ ├─────────┼─────────┼─────────┤   │ 风险与预警                 │
│      │ │ Card 4  │ Card 5  │ Card 6  │   │ ─────────────────────── │
│      │ └─────────┴─────────┴─────────┘   │ 关键事件                   │
│      │                                   │ ─────────────────────── │
│      │ Cross-Market Matrix               │ 推荐下钻                   │
│      │                                   │                           │
│      │ Macro Drivers Bar                 │                           │
│      ├───────────────────────────────────┴───────────────────────────┤
│      │ Bottom Tabs: [资金轮动] [事件日历] [AI 解读]                    │
│      │                                                                   │
└──────┴───────────────────────────────────────────────────────────────┘
```

### 3.4 与 Analytical 原版 Shell 的差异

| 维度 | Analytical 原版 | Radar 子变体 |
|------|----------------|-------------|
| Context 层 | 单层 Pulse Strip | 双层（Context Bar + Scope Strip） |
| 主工作面比例 | 65-70% | 固定 70% |
| 右侧 | Activity Stack | Right Rail（风险 + 事件 + 下钻） |
| 底部 | Analysis Band | Tab Band（资金轮动 / 事件日历 / AI 解读） |
| 页面动词 | 分析 / 监控 / 判断 | 扫描 / 比较 / 下钻 |

### 3.5 CSS Grid 定义

```css
.shell-radar {
  display: grid;
  grid-template-columns: var(--shell-rail-width) 1fr var(--shell-rail-radar-width);
  grid-template-rows: var(--shell-header-height) var(--context-bar-height) var(--scope-strip-height) 1fr var(--tab-band-height);
  grid-template-areas:
    "rail    header   header"
    "rail    context  context"
    "rail    scope    scope"
    "rail    main     right-rail"
    "rail    tabs     tabs";
}
```

---

## 4. 组件架构

### 4.1 组件树

```
CrossMarketOverviewPage
├── RadarShell (layout)
│   ├── WorkspaceHeader
│   │   ├── PageTitle ("Markets / 全市场总览")
│   │   ├── TimeFrameSelector ("1D" | "1W" | "1M")
│   │   ├── RefreshTimestamp ("09:46 CST")
│   │   ├── DensityToggle ("Compact" | "Comfortable")
│   │   └── SessionHint ("全球混合时段")
│   │
│   ├── ContextBar
│   │   ├── ContextPill ("GLOBAL Global")
│   │   ├── ContextPill ("SESSION Mixed")
│   │   ├── ContextPill ("REGIME Mild Risk-On")
│   │   ├── ContextPill ("VOLATILITY 回落")
│   │   ├── ContextPill ("DOLLAR 走弱")
│   │   └── AlertBadge (count: 2)
│   │
│   ├── ScopeStrip
│   │   ├── ScopeChip ("强势：港股科技/黄金")
│   │   ├── ScopeChip ("承压：美元/长债")
│   │   ├── ScopeChip ("风格：成长占优")
│   │   └── ScopeChip ("风险事件：FOMC-1D")
│   │
│   ├── MainStage (70%)
│   │   ├── CrossMarketCardGrid
│   │   │   ├── MarketCard (×6: A股/港股/美股/利率/外汇/商品)
│   │   ├── CrossMarketMatrix
│   │   │   └── MatrixRow (×6-8 市场, 6 列维度)
│   │   └── MacroDriversBar
│   │       └── MacroDriverBlock (×7: DXY/US10Y/CN10Y/VIX/Gold/Oil/CNY)
│   │
│   ├── RightRail (30%)
│   │   ├── MarketPulseSummary
│   │   ├── RiskAndAlertsPanel
│   │   ├── UpcomingEventsPanel
│   │   └── DrilldownRecommendations
│   │
│   └── BottomTabBand
│       ├── TabPanel: CapitalRotation
│       ├── TabPanel: EventCalendar
│       └── TabPanel: AIInsight
```

### 4.2 组件职责定义

#### ContextBar

- **类型**：Shell 级 context 组件
- **内容**：客观全局变量（Universe / Session / Regime / Volatility / Dollar / Alerts）
- **样式**：单行水平排列，每项用 `ContextPill`（label + value），`AlertBadge` 放末尾
- **数据**：规则引擎判断或 mock，不包含 A 股本地特定项（如北向流入）

#### ScopeStrip

- **类型**：Shell 级 context 组件
- **内容**：今日解读摘要（强势 / 承压 / 风格 / 风险事件）
- **样式**：单行水平排列，每项用 `ScopeChip`（短标签），颜色区分强势/承压/风险
- **数据**：规则引擎或 AI 生成

#### MarketCard

- **类型**：主工作面核心组件
- **每张卡片结构**：
  1. 市场名 + Regime Tag
  2. 核心指数 + 当日表现 + 相对强弱标签
  3. 一句话驱动摘要
  4. 下钻入口按钮
- **统一结构**：所有 6 张卡片使用完全相同的字段结构，只换数据
- **交互**：hover 状态提升、点击下钻

#### CrossMarketMatrix

- **类型**：主工作面比较组件
- **行**：市场/资产类别（6-8 行）
- **列**：1D / 1W / 1M / Vol / Breadth / Flow（6 列）
- **视觉**：热力矩阵风格，数值用颜色梯度表达强弱，文字保留精确值
- **交互**：行 hover 高亮对应 MarketCard

#### MacroDriversBar

- **类型**：主工作面驱动组件
- **每个 Driver Block**：名称 + 当前值 + 变化量 + 一句解释性标签
- **固定驱动器**：DXY / US10Y / CN10Y / VIX / Gold / Oil / USD/CNH

#### RightRail 四区块

| 区块 | 内容 | 行数限制 |
|------|------|---------|
| MarketPulseSummary | 每个市场一句话状态 | 4-5 行 |
| RiskAndAlertsPanel | 风险提示条 | 3-4 条 |
| UpcomingEventsPanel | 未来 24h/72h 关键事件 | 3-5 条 |
| DrilldownRecommendations | 动态下钻推荐（基于当前 cross-market state） | 3 条 |

#### BottomTabBand

| Tab | 内容 | 深度 |
|-----|------|------|
| 资金轮动 | 3 个 KPI + 流入/流出 top 3 + proxy flows + 一句总结 | 中等 |
| 事件日历 | 按时间分组（今夜/明日/本周），每条含影响市场 + 共识 + AI 预判 | 中等 |
| AI 解读 | 3 条跨市场主线总结，每条回答：发生了什么 / 为什么重要 / 该看哪里 | 轻量 |

---

## 5. 数据模型

### 5.1 类型定义（TypeScript）

```typescript
// ── Context Bar ──

interface GlobalContext {
  universe: "Global";
  session: "Asia Open" | "Mixed" | "Europe Pre-open" | "US Pre-market" | "US Open" | "US Closed";
  regime: "Strong Risk-On" | "Mild Risk-On" | "Mixed Rotation" | "Mild Risk-Off" | "Strong Risk-Off";
  volatility: "回落" | "稳定" | "抬升" | "飙升";
  dollar: "走强" | "稳定" | "走弱";
  alertCount: number;
}

// ── Scope Strip ──

interface ScopeItem {
  type: "strength" | "pressure" | "style" | "risk-event" | "warning";
  label: string;
}

// ── Market Card ──

type MarketId = "a-shares" | "hk" | "us" | "rates" | "fx" | "commodities";

type MarketRegime =
  | "Risk-On" | "Mild Risk-On" | "Mixed" | "Mild Risk-Off" | "Risk-Off"
  | "High Beta" | "Bonds Weak" | "Dollar Soft" | "Gold Lead";

interface MarketCardData {
  id: MarketId;
  name: string;
  regime: MarketRegime;
  benchmark: string;          // e.g. "沪深300"
  benchmarkChange: number;    // e.g. +0.67
  relativeStrength: string;   // e.g. "广度偏强"
  driver: string;             // e.g. "主线 AI+半导体"
  drilldownRoute: string;     // e.g. "/markets/a-shares"
  drilldownLabel: string;     // e.g. "进入 A 股总览"
}

// ── Cross-Market Matrix ──

interface MatrixRow {
  marketId: MarketId;
  marketName: string;
  change1d: number;
  change1w: number;
  change1m: number;
  volatility: "低" | "中低" | "中" | "中高" | "高";
  breadth: "弱" | "偏弱" | "中性" | "偏强" | "强" | "-";
  flowBias: string;           // e.g. "北向流入"
}

// ── Macro Driver ──

type MacroDriverId = "DXY" | "US10Y" | "CN10Y" | "VIX" | "Gold" | "Oil" | "USDCNH";

interface MacroDriver {
  id: MacroDriverId;
  name: string;
  value: string;              // e.g. "102.4" or "4.41%" or "+1.2%"
  change: string;             // e.g. "-0.4%" or "+7bp"
  interpretation: string;     // e.g. "美元走弱"
}

// ── Right Rail ──

interface PulseItem {
  marketId: MarketId;
  marketName: string;
  status: string;             // e.g. "Risk-On" / "弹性最强"
}

interface RiskAlert {
  id: string;
  severity: "high" | "medium" | "low";
  message: string;
}

interface UpcomingEvent {
  id: string;
  time: string;               // e.g. "今晚 20:30"
  name: string;               // e.g. "美国 CPI"
  affectedMarkets: string[];  // e.g. ["美股", "美债", "美元"]
  importance: "high" | "medium";
}

interface DrilldownRecommendation {
  marketId: MarketId;
  reason: string;             // e.g. "科技主线扩散"
  route: string;
  label: string;
}

// ── Bottom Tabs ──

interface CapitalRotation {
  riskAppetiteScore: number;  // 0-100
  equityVsDefense: string;    // e.g. "权益偏强"
  attractionShift: string;    // e.g. "美元→黄金"
  topInflows: string[];       // e.g. ["港股科技", "A股科技", "黄金"]
  topOutflows: string[];      // e.g. ["长债", "美元", "原油"]
  summary: string;
}

interface CalendarEvent {
  id: string;
  timeGroup: "今夜" | "明日" | "本周";
  time: string;
  name: string;
  affectedMarkets: string[];
  consensus: string;          // e.g. "按兵不动"
  riskDirection: string;      // e.g. "点阵图偏鹰"
}

interface AIInsight {
  id: string;
  order: number;
  what: string;               // 发生了什么
  why: string;                // 为什么重要
  whereToLook: string;        // 该看哪里
}

// ── Page-level aggregate ──

interface CrossMarketOverviewData {
  context: GlobalContext;
  scope: ScopeItem[];
  marketCards: MarketCardData[];
  matrix: MatrixRow[];
  macroDrivers: MacroDriver[];
  pulse: PulseItem[];
  riskAlerts: RiskAlert[];
  upcomingEvents: UpcomingEvent[];
  drilldownRecommendations: DrilldownRecommendation[];
  capitalRotation: CapitalRotation;
  calendarEvents: CalendarEvent[];
  aiInsights: AIInsight[];
  lastUpdated: string;        // ISO timestamp
}
```

### 5.2 Mock 数据策略

v1 所有数据使用 mock，Regime 判断规则引擎后续接入。

Mock 数据应覆盖：
- Risk-On 场景（默认）
- Risk-Off 场景
- Mixed Rotation 场景

---

## 6. 交互设计

### 6.1 TimeFrame 切换

- 支持 `1D / 1W / 1M`
- 切换时 Market Card 的 benchmark change、Matrix 的 1D/1W/1M 列同步更新
- 不触发整页刷新，仅更新受影响组件

### 6.2 Market Card 下钻

- 卡片整体可点击，hover 时显示视觉反馈（border 高亮 / 轻微提升）
- 底部下钻按钮为显式 CTA
- 下钻路由：A 股 → `/markets/a-shares`，港股/美股/其他 → 占位页或 `#`

### 6.3 Matrix 行交互

- hover 某行时，对应 Market Card 轻微高亮
- 点击行可触发排序或下钻

### 6.4 Right Rail 折叠

- 每个 Panel 支持折叠/展开
- 折叠状态记忆（localStorage）

### 6.5 Bottom Tabs

- 默认显示第一个 tab（资金轮动）
- Tab 切换不刷新上方内容
- Tab 内容区高度固定，超出滚动

### 6.6 响应式

| 断点 | 行为 |
|------|------|
| ≥1440px | 标准 70/30 布局 |
| 1024-1439px | 主内容 75%，Right Rail 收窄至 25% |
| 768-1023px | Right Rail 折叠到底部可展开面板 |
| <768px | 单列布局，Context Bar 横向滚动，Market Cards 2 列，Matrix 简化列 |

---

## 7. v1 范围

### 7.1 v1 必做

- 全市场总览完整页面（`/markets`）
- 6 个 Market Card（A股/港股/美股/利率/外汇/商品）
- Context Bar + Scope Strip
- Cross-Market Matrix
- Macro Drivers Bar
- Right Rail 四区块
- Bottom Tab Band（3 个 tab）
- Mock 数据覆盖
- A 股下钻连通（`/markets/a-shares`）
- 其他市场下钻为占位

### 7.2 v1 不做

- 港股/美股/商品/利率/外汇单市场页
- 加密市场
- 资金轮动中的真实 ETF/期货 proxy flows
- AI 解读的真实 AI 生成
- 事件日历的 AI 预判
- 深色模式适配（跟随全局暗色方案统一处理）

### 7.3 v1.5 扩展

- 港股总览页（`/markets/hk`）
- 港股下钻连通
- 资金轮动接入 proxy flows 数据

### 7.4 v2 扩展

- 美股总览页
- 商品/外汇/利率总览页
- 加密市场接入
- Regime 规则引擎真实数据
- AI 解读接入真实模型

---

## 8. 与现有设计体系的关系

### 8.1 复用的现有模式

- Context Bar 概念来自现有 Markets 页的 Scope Strip，但扩展为双层
- Right Rail 概念来自 Home 的右 rail，但聚焦市场投影与下钻
- Bottom Tab Band 概念来自 Intelligence 页的 tab 视图
- Market Card 复用 Object Hub 的 Meta Strip 语法

### 8.2 不复用的现有模式

- 不使用现有 Markets 页的 treemap/heatmap 作为主工作面
- 不使用现有 Markets 页的 ETF Matrix / Movers 作为核心组件
- 这些内容降级到单市场页（`/markets/a-shares`）中

### 8.3 新增的设计模式

- **双层 Context**：Context Bar（客观） + Scope Strip（解读）分离
- **Market Card 统一结构**：6 宫格平权比较
- **Cross-Market Matrix**：热力矩阵式跨市场比较器
- **Macro Drivers Bar**：驱动变量微型状态块
- **动态下钻推荐**：基于当前 cross-market state 推荐下钻入口

---

## 9. ASCII 线框（最终版）

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Markets / 全市场总览                                     [1D] [09:46 CST]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ GLOBAL | SESSION Mixed | REGIME Mild Risk-On | VOL 回落 | DXY 走弱 | A2    │
├──────────────────────────────────────────────────────────────────────────────┤
│ 强势：港股科技/黄金 | 承压：美元/长债 | 风格：成长占优 | 风险事件：FOMC-1D   │
├───────────────────────────────────────────────┬──────────────────────────────┤
│ 中国A股        港股          美股             │ 市场脉搏摘要                  │
│ Risk-On       High Beta     Mixed            │ A股 Risk-On                   │
│ +0.6%         +1.4%         +0.2%            │ 港股 最强                     │
│ 进入A股总览    进入港股总览   进入美股总览      │ 黄金 偏强                     │
├───────────────────────────────────────────────┤ 美元 走弱                     │
│ 利率           外汇          商品/黄金         ├──────────────────────────────┤
│ Bonds Weak    Dollar Soft   Gold Lead        │ 风险与预警                    │
│ US10Y +7bp    DXY -0.4%     Gold +1.2%       │ · FOMC前夜                    │
│ 进入利率页      进入外汇页     进入商品页       │ · 美债上行压成长              │
├───────────────────────────────────────────────┤ · A股科技拥挤                │
│ Cross-Market Matrix                           ├──────────────────────────────┤
│ 市场      1D   1W   1M   Vol   Breadth Flow   │ 关键事件                      │
│ A股      ...  ...  ...   ...   ...    ...    │ 今晚 CPI                      │
│ 港股      ...  ...  ...   ...   ...    ...    │ 明日 FOMC                     │
│ 美股      ...  ...  ...   ...   ...    ...    │ 本周中国社融                  │
│ 黄金      ...  ...  ...   ...    -     ...    ├──────────────────────────────┤
│ 原油      ...  ...  ...   ...    -     ...    │ 推荐下钻                      │
├───────────────────────────────────────────────┤ · 科技主线扩散 → A股总览       │
│ DXY | US10Y | CN10Y | VIX | Gold | Oil | CNY │ · 恒科弹性领先 → 港股总览     │
├───────────────────────────────────────────────┴──────────────────────────────┤
│ [资金轮动] [事件日历] [AI 解读]                                             │
│                                                                              │
│ 资金轮动：风险偏好迁移 + Proxy Flows                                        │
│ 事件日历：今夜/明日/本周                                                    │
│ AI 解读：3条跨市场主线总结                                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. 下一步

1. **评审本设计文档** — 确认页面结构、组件划分、数据模型
2. **同步更新上游文档** — 信息架构、Shell Family、Page Pattern Library、Component Spec
3. **创建实施计划** — 使用 writing-plans skill 生成开发任务分解
4. **TDD 实现** — 按组件逐个实现，先 mock 数据，后接真实 API
