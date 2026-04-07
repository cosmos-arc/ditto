# Shell-First 原型落地设计

> 日期: 2026-04-07
> 状态: Approved
> 范围: 将 17 个 HTML 原型的壳层体系落地为 React 运行时代码

---

## 1. 目标

将 Ditto 原型（17 页，均分 9.21/10）的壳层体系转换为 React 运行时代码：

- **像素级还原**原型布局（对照原型 HTML/CSS 源文件）
- **Shell-first**：先搭 6 类壳层 + 全局导航，再逐页填充
- **首期仅骨架**：不填充业务内容，只验证壳层体系可运行

---

## 2. 总体架构

### 2.1 架构分层

```
全局 Shell（AppShell）
├── Sidebar（固定左侧导航栏，6 大域 + 子菜单）
├── TopBar（当前域标题 + 用户/设置入口）
└── Content Area（<Outlet /> — 由 TanStack Router 渲染页面级壳层）

页面级壳层（6 类 Shell Layout）
├── CommandCenterShell    → / (Home)
├── AnalyticalShell       → /markets/*, /research/*, /trading/*
├── CatalogShell          → /markets/screener, /trading/signals
├── ObjectHubShell        → /instruments/:id, /strategies/:id
├── StudioShell           → /research/strategy-studio, /ai/*
└── OpsConsoleShell       → /platform/*
```

### 2.2 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 布局方式 | CSS Grid（从原型 layout-base.css 提取） | 原型已用 Grid 定义所有壳层，直接映射 |
| Shell 切换 | 路由级 Layout（TanStack Router layout routes） | 每个 Shell 是一个 layout.tsx，子路由自动嵌套 |
| 全局导航 | AppShell 作为 root layout | sidebar/topbar 固定，content 区域渲染子路由 |
| 样式策略 | Tailwind classes + Design Tokens | Token 体系已就绪，原型 CSS 规则映射为 Tailwind |
| 数据层 | 首期不接 API，用静态占位 | 骨架阶段，mock 数据后续迭代 |

---

## 3. 6 类壳层 Grid 结构映射

从原型 CSS（layout-base.css + 各页面 <style>）提取的完整壳层定义。

### 3.1 Command Center Shell（Home `/`）

```css
/* 原型: .shell */
grid-template-columns: var(--shell-rail-width) 1fr var(--shell-sidebar-width);  /* 56px 1fr 320px */
grid-template-rows: var(--shell-header-height) auto 1fr;                        /* 68px auto 1fr */
grid-template-areas:
  "rail header header"
  "rail pulse  pulse"
  "rail main   sidebar";
```

区域：Rail + Header + Pulse Strip + Main Content + Sidebar

### 3.2 Analytical Workspace Shell

```css
/* 原型: .shell-analytical */
grid-template-columns: var(--shell-rail-width) 1fr var(--shell-activity-width);       /* 56px 1fr 300px */
grid-template-rows: var(--shell-header-height) auto 1fr var(--shell-analysis-band-height); /* 68px auto 1fr 220px */
grid-template-areas:
  "rail header   header"
  "rail strip    strip"
  "rail main     activity"
  "rail analysis activity";
```

区域：Rail + Header + Scope Strip + Main Content + Activity Stack + Analysis Band

适用：/markets（Cross-Market, Intelligence）, /research, /trading（Overview, Risk）

变体：
- **Research**（.shell-research）：`Rail | 1fr`，无 Activity，带 tab-bar + main/secondary 上下分区
- **Risk**（.shell-risk）：`Rail | 1fr`，带 metrics strip（6 列）+ main/secondary 上下分区

### 3.3 Catalog Workspace Shell

```css
/* 原型: .shell-catalog */
grid-template-columns: var(--shell-rail-width) 1fr var(--shell-catalog-detail-width); /* 56px 1fr 320px */
grid-template-rows: var(--shell-header-height) auto 1fr;                             /* 68px auto 1fr */
grid-template-areas:
  "rail header  header"
  "rail toolbar toolbar"
  "rail table   detail";
```

区域：Rail + Header + Filter Toolbar + Table + Detail Panel

适用：/markets/screener, /trading/signals

变体：
- **Screener**（.shell-screener）：`Rail | 1fr`，无 Detail，带 toolbar + table + footer
- **Signals**（.shell-signals）：`Rail | 1fr | Detail(340px)`，带 toolbar + queue + detail

### 3.4 Object Hub Shell

```css
/* 原型: .shell-hub */
grid-template-columns: var(--shell-rail-width) 1fr;  /* 56px 1fr */
grid-template-rows: var(--shell-header-height) auto auto 1fr auto; /* 68px auto auto 1fr auto */
grid-template-areas:
  "rail header"
  "rail meta"
  "rail tabs"
  "rail main"
  "rail bottom";
```

区域：Rail + Header + Object Meta + Tab Bar + Main Content + Bottom

适用：/instruments/:id, /strategies/:id

### 3.5 Studio Shell（含 3 个变体）

#### Strategy Studio

```css
/* 原型: .shell-studio */
grid-template-columns: var(--shell-rail-width) 240px 1fr 300px;
grid-template-rows: var(--shell-header-height) auto 1fr var(--shell-status-bar-height);
grid-template-areas:
  "rail    header    header    header"
  "rail    header2   header2   header2"
  "rail    sources   main      inspector"
  "rail    logs      logs      logs";
```

区域：Rail + Header + Secondary Header + Sources Panel + Main Editor + Inspector Panel + Logs

#### AI Copilot

```css
/* 原型: .shell-copilot */
grid-template-columns: var(--shell-rail-width) 220px 1fr 280px;
grid-template-rows: var(--shell-header-height) auto 1fr;
grid-template-areas:
  "rail header header header"
  "rail modes  modes  modes"
  "rail sessions conversation context";
```

区域：Rail + Header + Mode Strip + Sessions Panel + Conversation + Context Panel

#### Agent Console

```css
/* 原型: .shell-agent */
grid-template-columns: var(--shell-rail-width) 1fr 340px;
grid-template-rows: var(--shell-header-height) auto 1fr;
grid-template-areas:
  "rail header header"
  "rail tabs   tabs"
  "rail main   detail";
```

区域：Rail + Header + Agent Tabs + Main Content + Detail Panel

### 3.6 Operations Console Shell

```css
/* 原型: .shell-ops */
grid-template-columns: var(--shell-rail-width) 1fr var(--shell-ops-detail-width); /* 56px 1fr 340px */
grid-template-rows: var(--shell-header-height) auto 1fr;                         /* 68px auto 1fr */
grid-template-areas:
  "rail header header"
  "rail health health"
  "rail main   detail";
```

区域：Rail + Header + Health Strip + Main Content + Detail Panel

适用：/platform

---

## 4. React 组件架构

### 4.1 组件层级

```
<__root.tsx>                          ← 全局 Provider 层
  <AppShell>                          ← 全局壳层：Rail + Header + <Outlet />
    <Rail>                            ← 左侧 56px 图标导航
    <Header>                          ← 顶部栏（标题动态切换）
    <div id="content-area">
      <Outlet />                      ← TanStack Router 渲染页面级壳层
    </div>
  </AppShell>
```

### 4.2 目录结构

```
src/
├── features/
│   ├── shell/                        ← 壳层系统
│   │   ├── components/
│   │   │   ├── app-shell.tsx         ← 全局壳层容器
│   │   │   ├── rail.tsx              ← 左侧图标导航
│   │   │   ├── header.tsx            ← 顶部栏
│   │   │   ├── panel.tsx             ← 通用面板（header/body/actions）
│   │   │   └── noise-layer.tsx       ← Noise + Ambient 装饰层
│   │   ├── layouts/
│   │   │   ├── command-center.layout.tsx
│   │   │   ├── analytical.layout.tsx
│   │   │   ├── catalog.layout.tsx
│   │   │   ├── object-hub.layout.tsx
│   │   │   ├── studio.layout.tsx     ← 含 strategy/copilot/agent 变体
│   │   │   └── ops-console.layout.tsx
│   │   └── hooks/
│   │       └── use-active-domain.ts  ← 当前活跃域状态
│   └── navigation/
│       ├── components/
│       │   └── domain-icon.tsx       ← 域图标（6 个 SVG）
│       └── types.ts
├── routes/
│   ├── __root.tsx                    ← 渲染 <AppShell>
│   ├── index.tsx                     ← Home (/)
│   ├── markets/
│   │   ├── layout.tsx                ← AnalyticalShell
│   │   ├── index.tsx
│   │   ├── screener.tsx              ← 覆盖为 CatalogShell
│   │   └── intelligence.tsx
│   ├── research/
│   │   ├── layout.tsx                ← AnalyticalShell（带 tab-bar 变体）
│   │   ├── index.tsx
│   │   └── regime.tsx
│   ├── trading/
│   │   ├── layout.tsx                ← AnalyticalShell
│   │   ├── index.tsx
│   │   ├── signals.tsx               ← 覆盖为 CatalogShell
│   │   ├── orders.tsx
│   │   └── risk.tsx
│   ├── ai/
│   │   ├── layout.tsx                ← StudioShell 共享变体
│   │   ├── index.tsx                 ← AI Overview
│   │   ├── copilot.tsx
│   │   └── agents.tsx
│   ├── instruments/
│   │   ├── layout.tsx                ← ObjectHubShell
│   │   └── $id.tsx
│   └── platform/
│       ├── layout.tsx                ← OpsConsoleShell
│       └── index.tsx
```

### 4.3 样式映射策略

| 原型写法 | React/Tailwind 写法 |
|---------|-------------------|
| `display: grid; grid-template-columns: 56px 1fr 320px` | `grid` + `grid-cols-[var(--shell-rail-width)_1fr_var(--shell-sidebar-width)]` |
| `var(--surface-app)` | `bg-[var(--surface-app)]` |
| `var(--border-subtle)` | `border-[var(--border-subtle)]` |
| `var(--space-8)` / `var(--space-16)` | 直接用 CSS 变量保持精确映射 |
| `var(--font-size-12)` | `text-[var(--font-size-12)]` |

关键原则：壳层 Grid 使用 Tailwind arbitrary values + CSS 变量，与原型 Token 保持 1:1 映射，不硬编码像素值。

---

## 5. 共享元素

### 5.1 Rail（全局共享）

- 56px 宽，居中图标 + logo
- 6 个域图标：Home / Markets / Research / Trading / AI / Platform
- Active 状态：brand-accent 背景 + 左侧竖条 + glow
- 底部：设置/用户图标

### 5.2 Header（全局共享）

- 68px 高，frosted glass 背景（部分页面）
- 左侧：当前页面标题（动态切换）
- 中间：spacer
- 右侧：搜索框 + 通知 + 主题切换 + avatar

### 5.3 Panel 基础组件

- `panel-header`：标题 + 副标题 + actions
- `panel-body`：flex:1, overflow-y:auto
- `panel-action`：hover 交互按钮

### 5.4 装饰层（Graphite Studio 风格）

- **Noise texture**：SVG filter + 0.018 opacity 覆盖层
- **Ambient light bars**：顶部/右侧渐变光条（brand-accent 低透明度）
- **Header bottom accent**：frosted glass + 底部品牌色渐变线

---

## 6. 首期交付物

### 包含

- [ ] 6 类 Shell Layout 组件（Grid 骨架，内容区为占位 div）
- [ ] AppShell（Rail + Header + Outlet）
- [ ] 路由文件（所有 layout.tsx + 空页面）
- [ ] Noise/Ambient 装饰层
- [ ] Panel 基础组件
- [ ] 域导航图标（6 个 SVG）
- [ ] 壳层布局的像素级还原（Grid 尺寸与原型一致）

### 不包含

- [ ] 业务组件（Decision Banner、Signal Queue 等）
- [ ] 数据层（API 接入、TanStack Query hooks）
- [ ] Mock 数据
- [ ] 具体页面内容
- [ ] 状态变体（loading/empty/error）
- [ ] 交互动画（Sparkline、NumberTicker 等）

---

## 7. 验证标准

首期完成后的验证方式：

1. **路由可走通**：所有 17 个页面路由可访问，显示正确的壳层骨架
2. **壳层正确**：每个页面使用对应的 Shell Layout，Grid 结构与原型一致
3. **导航联动**：Rail 点击切换域，Header 标题随路由变化
4. **Token 对齐**：所有尺寸、颜色使用 CSS 变量，与原型 Token 1:1
5. **`bun run check` 通过**：lint + type + test 全绿
