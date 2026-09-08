# Edition v1 全量原型创建方案

> 日期：2026-04-01
> 状态：待执行

## 目标

基于 IA 蓝图，全量创建 v1 Edition 的 14 个核心页面原型，统一命名规则，清理遗留文件，并在每个页面内集成密度切换和 Light/Dark 主题切换功能。

---

## 设计决策

### 1. 命名规则

```
page-{domain}.html                  # 一级入口页面
page-{domain}-{feature}.html        # 二级功能页面
```

| 示例 | 说明 |
|------|------|
| `page-home.html` | 首页（一级入口） |
| `page-markets-screener.html` | 市场筛选器（二级功能） |
| `page-trading-overview.html` | 交易总览（二级功能） |

### 2. 密度 & 主题切换

- **不创建独立的密度变体文件**
- 每个页面原型右上角集成切换按钮组：密度（紧凑/标准/宽松）+ 主题（亮/暗）
- 通过 JS 修改 CSS 变量实现实时切换
- 3 级密度：Dense(34px rows) / Compact(36px rows, 默认) / Comfortable(42px rows)
- 2 种主题：Dark(默认) / Light

### 3. 遗留文件清理

- 删除全部 4 个 legacy 文件
- 删除 2 个独立的密度变体文件（`prototype-dense.html`, `prototype-comfortable.html`）

---

## 页面清单（14 页）

### Batch 1 — 核心入口（6 页）

| # | 文件名 | 页面 | 路由 | Shell | Pattern | 状态 |
|---|--------|------|------|-------|---------|------|
| 1 | `page-home.html` | 首页 | `/` | Command Center | Global Command Center | 重命名+升级 |
| 2 | `page-cross-market.html` | 全市场总览 | `/markets` | Analytical | Analytical Overview (Radar) | 保留(9.33) |
| 3 | `page-markets-screener.html` | 市场筛选器 | `/markets/screener` | Catalog | Catalog / Screener | 保留(首稿) |
| 4 | `page-research.html` | 研究工作区 | `/research` | Analytical | Analytical Overview | 保留(需精修) |
| 5 | `page-trading-overview.html` | 交易总览 | `/trading` | Analytical | Analytical Overview | 重命名 |
| 6 | `page-platform.html` | 平台运维 | `/platform` | Ops Console | Queue / Ops Console | 保留(9.50) |

### Batch 2 — 形成闭环（3 页）

| # | 文件名 | 页面 | 路由 | Shell | Pattern | 状态 |
|---|--------|------|------|-------|---------|------|
| 7 | `page-instrument-hub.html` | 标的详情 | `/instruments/[id]` | Object Hub | Object Hub | 新建 |
| 8 | `page-strategy-studio.html` | 策略工作室 | `/research/strategies/[id]/studio` | Studio | Studio / Builder | 新建 |
| 9 | `page-signals-inbox.html` | 信号收件箱 | `/trading/signals` | Ops Console | Queue / Ops Console | 新建 |

### Batch 3 — 深度页面（5 页）

| # | 文件名 | 页面 | 路由 | Shell | Pattern | 状态 |
|---|--------|------|------|-------|---------|------|
| 10 | `page-orders-ledger.html` | 执行账本 | `/trading/orders` | Ops Console | Ledger / Execution | 新建 |
| 11 | `page-risk-center.html` | 风控中心 | `/trading/risk` | Analytical | Analytical Overview | 新建 |
| 12 | `page-ai-overview.html` | AI 总览 | `/ai` | Command Center | Command Center (light) | 新建 |
| 13 | `page-ai-copilot.html` | AI Copilot | `/ai/copilot` | Studio | Studio / Builder | 新建 |
| 14 | `page-agent-console.html` | Agent 控制台 | `/ai/agent` | Studio | Studio / Builder | 新建 |

---

## 文件变更清单

### 重命名（3 个）

| 原文件 | 新文件 |
|--------|--------|
| `prototype-compact.html` | `page-home.html` |
| `page-markets.html` | `page-markets-dashboard.html`（删除，内容合并到 page-cross-market） |
| `page-trading.html` | `page-trading-overview.html` |

> 注意：`page-markets.html`（行情仪表盘）与 `page-cross-market.html`（全市场总览）功能重叠。
> 根据蓝图，`/markets` 就是 Cross-Market Overview，热力图是其中子视图。
> 决定：删除 `page-markets.html`，热力图内容合并到 cross-market 作为 tab 切换视图。

### 删除（6 个）

| 文件 | 原因 |
|------|------|
| `research_legacy.html` | 已替代 |
| `screener_legacy.html` | 已替代 |
| `signals_legacy.html` | v1 新建替代 |
| `risk_legacy.html` | v1 新建 page-risk-center 替代 |
| `prototype-dense.html` | 密度切换改为页面内功能 |
| `prototype-comfortable.html` | 密度切换改为页面内功能 |
| `page-markets.html` | 功能合并到 cross-market |
| `style-b-graphite-studio/index.html` | 密度导航页不再需要（无独立变体） |

### 新建（8 个）

1. `page-instrument-hub.html`
2. `page-strategy-studio.html`
3. `page-signals-inbox.html`
4. `page-orders-ledger.html`
5. `page-risk-center.html`
6. `page-ai-overview.html`
7. `page-ai-copilot.html`
8. `page-agent-console.html`

### 保留不动（10 个）

- `page-cross-market.html` — 已完成，升级加入切换功能
- `page-markets-screener.html` — 首稿，升级加入切换功能
- `page-research.html` — 需精修，升级加入切换功能
- `page-platform.html` — 已完成，升级加入切换功能
- `style-b-graphite-studio/token-showcase.html` — 设计系统参考
- `tokens-style.css` — Style B 样式
- `shared/` — 全部共享样式文件

---

## 密度 & 主题切换实现方案

### 切换控件位置

页面 Header 右侧，搜索框和用户头像之间。

### 切换控件样式

```
[紧凑] [标准] [宽松]   |   [🌙 暗] [☀️ 亮]
   密度切换组          |    主题切换组
```

### CSS 变量切换机制

```html
<html data-density="compact" data-theme="dark">
```

- 密度切换：修改 `data-density` 属性（dense / compact / comfortable）
- 主题切换：修改 `data-theme` 属性（dark / light）
- CSS 中使用属性选择器 `[data-density="dense"]` / `[data-theme="light"]` 覆盖变量

### Light 主题 Token

基于现有 Dark Token 反转，核心映射：

| Dark Token | Light Token | 说明 |
|------------|------------|------|
| `--surface-0: oklch(0.15 ...)` | `oklch(0.98 ...)` | 主背景 |
| `--surface-1: oklch(0.18 ...)` | `oklch(0.95 ...)` | 卡片背景 |
| `--text-primary: oklch(0.92 ...)` | `oklch(0.15 ...)` | 主文字 |
| `--border-subtle: oklch(0.25 ...)` | `oklch(0.88 ...)` | 边框 |

---

## 执行步骤

### Phase 1: 清理 & 重命名
1. 删除 6 个遗留/废弃文件
2. 重命名 `prototype-compact.html` → `page-home.html`
3. 重命名 `page-trading.html` → `page-trading-overview.html`
4. 更新 `.edition-manifest.json`

### Phase 2: 共享切换组件
5. 在 `shared/` 中创建切换组件的 CSS + JS
6. 在 `shared/tokens-theme.css` 中添加 Light 主题 token

### Phase 3: 升级已有页面
7. 为 4 个已保留页面集成密度/主题切换按钮
8. 精修 `page-research.html`

### Phase 4: 新建 Batch 2 页面（3 页）
9. `page-instrument-hub.html`
10. `page-strategy-studio.html`
11. `page-signals-inbox.html`

### Phase 5: 新建 Batch 3 页面（5 页）
12. `page-orders-ledger.html`
13. `page-risk-center.html`
14. `page-ai-overview.html`
15. `page-ai-copilot.html`
16. `page-agent-console.html`

### Phase 6: 验证
17. 跨页面一致性审计
18. 更新 `.edition-manifest.json` 最终状态

---

## 参考文档

- [IA 信息架构](design/specs/01_product_information_architecture.md) v1.1
- [核心页面蓝图](design/specs/02_core_page_blueprints.md) v1.2
- [Shell 规范](design/specs/10_ditto_shell_family_spec.md) v1.2
- [页面模式库](design/specs/11_ditto_page_pattern_library.md) v1.2
- [核心用户流程](design/specs/06_core_user_flows.md) v1.2
- [关键设计决策](docs/designs/decisions/2026-03-28-key-design-decisions.md)
- [Edition Manifest](prototype/.edition-manifest.json)
