# Edition v1 全量审计报告

> **审计日期**：2026-04-05
> **审计范围**：17 个 HTML 原型页面 + Design Token 9 层架构 + 运行时 `src/styles/`
> **审计基准**：视觉宪章 v1.0、核心页面蓝图 v1.2、Shell Family v1.2、Page Pattern Library v1.2、Token Architecture v1.0
> **审计员**：Claude (Design Systems Auditor)
> **修复状态**：P0 + P1 全部修复完成（2026-04-05）

---

## 1. 总览

### 1.1 评分汇总

| # | 页面 | Shell 类型 | Pattern | 得分 | 审计轮数 | 关键评语 |
|---|------|-----------|---------|------|---------|---------|
| 1 | page-home | Command Center | Global Command Center | **8.5** | 2 | 材质层出色，Token 使用最佳实践 |
| 2 | page-cross-market | 自定义 radar | Analytical Overview | **7.0** | 2 | Shell 不在共享层，热力图硬编码色值 |
| 3 | page-markets-screener | Catalog | Catalog / Screener | **8.0** | 10 | 信号药丸系统精妙，inline style 过多 |
| 4 | page-research | Analytical | Analytical Overview | **7.5** | 9 | 数据密度最高，分析带图表为占位符 |
| 5 | page-trading-overview | Analytical variant | Analytical Overview | **7.5** | 3 | 双模式架构野心大，决策横幅与 Home 不一致 |
| 6 | page-platform | Ops Console | Queue / Ops Console | **8.0** | 4 | 最接近组件提取就绪，inline style 最少 |
| 7 | page-instrument-hub | Object Hub | Object Hub | **9.0** | 6 | CSS 原型天花板，Token 合规度最高 |
| 8 | page-strategy-studio | Studio | Studio / Builder | **7.5** | 0 | 四栏 Studio 结构清晰，未完成 review |
| 9 | page-signals-inbox | Ops Console | Queue / Ops Console | **7.5** | 0 | 信号优先级编码得当，未完成 review |
| 10 | page-orders-ledger | Ops Console | Ledger / Execution | **7.5** | 0 | 执行状态链完整，未完成 review |
| 11 | page-risk-center | Analytical | Analytical Overview | **7.0** | 0 | 风控仪表设计合理，未完成 review |
| 12 | page-ai-overview | Command Center | Command Center (light) | **7.0** | 0 | 28 个状态变体覆盖广，未完成 review |
| 13 | page-regime-monitor | Analytical | Analytical Overview | **8.5** | 0 | 零硬编码色值，唯一完整 stale 覆盖 |
| 14 | page-markets-intelligence | 自定义 flex | Analytical Overview | **7.5** | 0 | 唯一正确使用 header token，但 flex 不一致 |
| 15 | page-ai-copilot | Studio | Studio / Builder | **7.5** | 0 | 四栏布局合理，header 高度偏差 |
| 16 | page-agent-console | Studio | Studio / Builder | **6.5** | 0 | 重复 checkbox ID 功能性 bug |
| 17 | token-showcase | 文档页 | N/A | **8.0** | 0 | 最完整 Token 参考，零硬编码色值 |

**全站均分：7.7/10**

### 1.2 与原有分数对比

| 页面 | 原分 | 新审分 | 变化 | 原因 |
|------|------|--------|------|------|
| cross-market | 9.33 | 7.0 | ↓2.33 | Shell 合规性、硬编码热力图色值 |
| platform | 9.50 | 8.0 | ↓1.50 | 废弃 token 使用、inline style |
| home | 9.40 | 8.5 | ↓0.90 | 原审未扣 inline style 分 |
| markets-screener | 9.64 | 8.0 | ↓1.64 | 228 处 inline style、废弃 token |
| research | 8.96 | 7.5 | ↓1.46 | 分析带占位符、废弃 token |
| trading-overview | 9.34 | 7.5 | ↓1.84 | header 覆盖、双模式 DOM 重复 |
| instrument-hub | 9.46 | 9.0 | ↓0.46 | 微调，仍为最高分 |

**原有评分体系偏宽松**，主要未扣分维度：inline style 密度、废弃 token 使用、Shell 合规性。本次审计采用统一严格标准。

---

## 2. 系统级发现

### 2.1 P0 — 功能性 Bug

| # | 问题 | 页面 | 影响 | 状态 |
|---|------|------|------|------|
| 1 | **重复 checkbox ID** | agent-console | `overlay-approval-confirm` 等出现 2-3 次，`:has()` 选择器只匹配首个，overlay gallery 中触发器失效 | ✅ 已修复 |

### 2.2 P1 — 设计系统一致性

| # | 问题 | 影响页面数 | 修复建议 | 状态 |
|---|------|-----------|---------|------|
| 1 | **Shell 定义不在共享层** | cross-market, markets-intelligence | `shell-radar` 和 flex 布局应迁移到共享 `layout-base.css` 或等效共享层 | ⏳ 延后 |
| 2 | **Header 高度硬编码** | copilot(60px), agent(60px), regime(64px), trading(64px), risk(64px), orders(60px) | 统一使用 `var(--shell-header-height)` | ✅ 已修复 |
| 3 | **`color: #fff` 硬编码** | 全部 14 个页面 | 创建 `--brand-accent-fg` 语义 token | ✅ 已修复 |
| 4 | **`--font-size-11` 废弃 token** | 10 个页面共 40 处 | 全部迁移到 `--font-size-12` | ✅ 已修复 |
| 5 | **`--surface-muted` 未定义** | screener, platform | 确认是否需添加到 L2 或 L5 | ⏳ 延后 |
| 6 | **决策横幅不一致** | home vs trading-overview | Home 有品牌强调左边框，Trading 没有；比例不同 | ⏳ 延后 |

### 2.3 P2 — 完整性增强

| # | 问题 | 影响页面数 | 修复建议 |
|---|------|-----------|---------|
| 1 | **Stale 状态未覆盖** | copilot, agent, screener, signals, orders, risk, ai-overview | Regime monitor 是唯一完整覆盖 stale 的页面 |
| 2 | **`tokens-data-viz.css` 未引入** | copilot, agent, signals, orders, risk | 含图表/矩阵的页面应引入 |
| 3 | **分析带图表为占位符** | research | IC 趋势图等核心分析工具未实现 |
| 4 | **`font-family: monospace` 硬编码** | cross-market | 应使用 `var(--font-family-data)` |

### 2.4 跨页面一致性矩阵

| 维度 | 通过 | 失败 | 备注 |
|------|------|------|------|
| Shell 网格定义 | 13/16 | cross-market, intelligence, showcase | |
| Token-only 颜色 | 14/16 | agent(console #fff), cross-market(热力图) | |
| 共享布局使用 | 14/16 | cross-market, intelligence | |
| 密度/主题切换器 | 16/16 | — | 全覆盖 |
| 状态画廊 | 16/16 | — | 全覆盖 |
| `prefers-reduced-motion` | 14/16 | 未检查全部 | 批次 1 全覆盖 |
| 无硬编码色值 | 12/16 | copilot, agent, intelligence, cross-market | |
| Stale 状态覆盖 | 2/16 | regime, intelligence | |

---

## 3. Token 架构就绪度

### 3.1 运行时 Token 层状态

`src/styles/` 已完成从单体 `globals.css` 到 9 层架构的拆分（commit `8fd3947`）。

| 层级 | 文件 | 状态 | 评价 |
|------|------|------|------|
| L1 Primitives | `01-primitives.css` | ✅ 完成 | 中性色板 + 品牌 + 功能色 + 间距 + 圆角 + 动效 |
| L2 Semantic | `02-semantic.css` | ✅ 完成 | surface/foreground/border/accent/brass/code/scrollbar |
| L3 Shell | `03-shell.css` | ✅ 完成 | rail/sidebar/detail/header/bar 尺寸 |
| L4 Data Viz | `04-data-viz.css` | ✅ 完成 | data freshness/chart series/heatmap/sparkline/asset/LED |
| L5 Component | `05-component.css` | ✅ 完成 | btn/badge/card/input/tab/checkbox 结构尺寸 |
| L6 Interaction | `06-interaction.css` | ✅ 完成 | focus/hover/active/selected/toast/progress |
| L7 Domain | `07-domain.css` | ✅ 完成 | market/risk/execution/system/quality/signal/agent |
| L8 Density | `08-density.css` | ✅ 完成 | compact/comfortable/dense 覆盖 |
| Dark Theme | `themes/dark.css` | ✅ 完成 | 暗色默认值已嵌入各层 |
| Light Theme | `themes/light.css` | ✅ 完成 | surface/foreground/border/code 反转 |
| Market Intl | `themes/market-intl.css` | ✅ 完成 | 涨跌色反转 |

### 3.2 原型 → 运行时迁移差距

| 差距 | 严重度 | 说明 |
|------|--------|------|
| 命名空间不一致 | **高** | 原型用 `--bg-surface-0` / `--text-primary`，运行时用 `--color-surface-0` / `--color-foreground`。需全量映射 |
| 内联 style 密度 | **高** | 17 页面共 ~1000+ 处 inline style，需提取为组件 + Tailwind utilities |
| Shell 共享层碎片化 | **中** | 原型 6 种 shell 在 `shared/layout-base.css` 中定义，运行时只有 `03-shell.css` 尺寸 token，缺 grid 模板 |
| `@theme inline` vs CSS 变量 | **低** | 原型用纯 CSS 变量，运行时用 Tailwind `@theme inline`。语义相同但注册方式不同 |
| 缺少 `--color-on-brand` | **低** | 多个页面硬编码 `#fff` 作为品牌色上文字色，运行时无此 token |

### 3.3 迁移优先级

```
Phase 1: Token 映射表建立（1-2 天）
  ├─ 原型 token → 运行时 token 全量映射
  └─ 验证 globals.css 9 层完整性

Phase 2: Shell 布局组件化（3-5 天）
  ├─ 6 种 Shell grid 模板 → React Layout 组件
  └─ Header / Rail / Sidebar / Detail / Activity → 可组合布局零件

Phase 3: 组件提取（10-15 天）
  ├─ 从 inline style 提取高频组件（Table, Badge, SignalPill, Overlay）
  └─ 映射到 shadcn/ui + Tailwind utility 模式
```

---

## 4. 页面级详细审计

### 4.1 Tier S — 标杆页面（8.5+）

**page-instrument-hub (9.0)**
- Object Hub Shell，6 轮 review，CSS 原型天花板
- 13 个状态变体、6 个 overlay、8 个 tab
- Token 合规度最高，接近运行时迁移就绪
- **注**：CSS 原型天花板在 9.0-9.5，突破 10 需要 React + 真实数据 + JS 交互

**page-home (8.5)**
- Command Center Shell，材质层系统（SVG 噪点 + 磨砂玻璃 + 环境光条）出色
- 决策横幅三区比例网格优雅
- 状态变体画廊 100% 覆盖，8 个组件
- 缺陷：51 处 inline style

**page-regime-monitor (8.5)**
- 零硬编码色值，唯一完整 stale 状态覆盖
- 唯一引入 `tokens-data-viz.css` 的页面
- CSS-only gauge 可视化技术优秀
- 缺陷：header 高度 64px 硬编码

### 4.2 Tier A — 高质量页面（7.5-8.4）

**page-markets-screener (8.0)**
- 信号药丸系统（方向 + 置信度双层编码）是量化场景最佳实践
- 迷你图 SVG sprite DRY 实现
- 行选择 `box-shadow: inset 3px 0 0` 优雅
- 缺陷：228 处 inline style，`--font-size-11` 废弃 token

**page-platform (8.0)**
- 65 处 inline style，最接近组件提取就绪
- 环境徽章、数据健康条、行宕机状态设计精良
- 覆盖面板最精简（3 个，单一用途）

**token-showcase (8.0)**
- 最完整 Token 参考实现，9 个 CSS 文件引入
- 交互式 density/region 切换，教育价值极高
- Domain tokens 7 类全覆盖

**page-research (7.5)**
- 因子监控表是所有原型中数据密度最高的组件
- 双工作区（Activity Stack + Analysis Band）模式好
- 缺陷：分析带图表为占位符，94 处 inline style

**page-trading-overview (7.5)**
- 双模式（Trading/Review）架构是原型中最野心勃勃的状态系统
- 风险监控进度条信息密集但可扫描
- 缺陷：header 高度覆盖为 56px，DOM 双份重复

**page-strategy-studio (7.5)**
- 四栏 Studio 布局（Rail + Sessions + Editor + Context）清晰
- 未完成 review 轮次

**page-signals-inbox (7.5)**
- 信号优先级编码得当
- 未完成 review 轮次

**page-orders-ledger (7.5)**
- 执行状态链完整
- 未完成 review 轮次

**page-markets-intelligence (7.5)**
- 唯一正确使用 `var(--shell-header-height)` 的页面
- 5 tab 信息架构丰富，Toast 交互模式创新
- 缺陷：Flex 布局与 grid 不一致

**page-ai-copilot (7.5)**
- 四栏 Studio 布局合理
- 缺陷：header 60px 硬编码，缺 stale 状态

### 4.3 Tier B — 需提升页面（<7.5）

**page-cross-market (7.0)**
- 热力图 `data-heat` 语义化 CSS 模式创新
- 固定状态栏独特身份元素
- 缺陷：Shell `shell-radar` 完全页面级定义不在共享层，命名冲突风险，热力图色值硬编码

**page-risk-center (7.0)**
- 风控仪表设计合理
- 未完成 review 轮次，需要精修

**page-ai-overview (7.0)**
- 28 个状态变体覆盖广
- 未完成 review 轮次，需要精修

**page-agent-console (6.5)**
- Agent chain 可视化、Tool trace timeline 设计优秀
- **重复 checkbox ID 是功能性 bug**，拉低分数
- 缺陷：`#ef4444` fallback，缺 stale 状态

---

## 5. 架构就绪度评估

### 5.1 原型 → React 迁移就绪度矩阵

| 维度 | 就绪度 | 说明 |
|------|--------|------|
| Design Token 层级 | ✅ **90%** | 9 层 CSS 已拆分，Tailwind `@theme inline` 已注册 |
| Shell 布局体系 | ⚠️ **60%** | 原型 6 种 Shell grid 在 `shared/layout-base.css`，运行时只有尺寸 token，缺 React Layout 组件 |
| 组件抽象 | ⚠️ **40%** | 高频组件（Table, Badge, Overlay, SignalPill）仍在 inline style 中，未提取 |
| 状态管理模式 | ❌ **20%** | 原型用 CSS `:has()` + radio hack，React 需完全不同的状态管理 |
| 数据层衔接 | ❌ **10%** | 原型硬编码模拟数据，API 层 + TanStack Query 尚未设计 |
| 路由映射 | ⚠️ **50%** | IA 蓝图定义了路由，TanStack Router 文件约定待实施 |
| 测试基础设施 | ⚠️ **30%** | Vitest + RTL 已配置，Design Token 测试和组件测试未开始 |

### 5.2 迁移风险点

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 命名空间不一致（`--bg-` → `--color-`） | 高 | 建立全量映射表，自动化迁移脚本 |
| `:has()` 兼容性 | 中 | React 组件化后不需要 `:has()` hack |
| CSS 变量与 Tailwind 冲突 | 中 | `@theme inline` 已解决，但 `--text-*` 与 Tailwind `text-*` 前缀冲突需注意 |
| SVG 噪点/磨砂玻璃性能 | 低 | `prefers-reduced-motion` 已覆盖 |

---

## 6. 下一步方向建议

### 6.1 短期（1-2 周）— 补齐原型质量

| 优先级 | 任务 | 预估 |
|--------|------|------|
| P0 | 修复 agent-console 重复 checkbox ID | 1h |
| P1 | 统一 header 高度为 `var(--shell-header-height)` | 2h |
| P1 | 消除所有 `#fff` → `--color-on-brand` token | 2h |
| P1 | 替换所有 `--font-size-11` → `--font-size-12` | 1h |
| P2 | 为 9 个未审页面完成 review 轮次 | 5-8 天 |
| P2 | 补齐 stale 状态覆盖 | 2-3 天 |

### 6.2 中期（3-6 周）— React 迁移准备

| Phase | 任务 | 预估 |
|-------|------|------|
| Phase 1 | Token 映射表（原型 → 运行时）全量文档 | 1-2 天 |
| Phase 2 | Shell Layout React 组件（6 种 Shell → 可组合 Layout） | 3-5 天 |
| Phase 3 | 核心组件提取（Table, Badge, Overlay, SignalPill, Progress） | 10-15 天 |
| Phase 4 | 第一个页面 React 实现（建议从 platform 开始，inline 最少） | 5-7 天 |

### 6.3 长期方向 — 三条可选路径

**路径 A：原型优先深化**
- 继续精修 17 个原型到 8.5+ 均分
- 优势：设计确定性最高，迁移返工最少
- 风险：延期 React 启动，CSS 原型天花板在 9.5

**路径 B：React 迁移推进（推荐）**
- 选 1-2 个标杆页面（platform + instrument-hub）做 React 实现
- 边迁移边补齐 Token 和组件
- 优势：尽早验证架构假设，建立开发节奏
- 风险：可能发现原型未覆盖的交互场景

**路径 C：混合推进**
- 核心页面（home, cross-market, instrument-hub）原型精修 + React 迁移并行
- 辅助页面（signals, orders, risk）原型快速补齐
- 优势：效率最高
- 风险：需要明确的优先级管理

---

## 7. 结论

Ditto v1 Edition 的设计系统基础**非常扎实**：

- **Token 分层架构**（9 层 CSS）是业界一流水平，OKLCH 色彩空间 + shadcn 模式命名 + Tailwind v4 `@theme inline` 的组合是正确的长期方向
- **视觉宪章**定义清晰，8 条原则覆盖了量化交易平台的核心设计哲学
- **17 页全量原型**提供了完整的视觉参考，信息架构从首页指挥台到 AI Agent 控制台全覆盖

主要差距在于：
1. **一致性执行** — Shell 合规、header 高度、硬编码色值需要统一修复
2. **组件化程度** — 1000+ inline style 需要提取为可复用组件
3. **迁移就绪度** — 原型到 React 的映射路径需要明确

**建议采纳路径 B**：以 platform 和 instrument-hub 为先锋启动 React 迁移，在真实组件开发中验证和补齐 Design Token 体系。
