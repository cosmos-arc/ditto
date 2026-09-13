# AI Overview 三区修复设计

**日期**: 2026-04-11
**状态**: 已确认
**关联计划**: `2026-04-11-prototype-pixel-replica-plan.md` Task 5

## 问题诊断

React `/ai` 与 prototype `page-ai-overview.html` 存在三层结构偏差：

| 区域 | Prototype | React | 偏差 |
|------|-----------|-------|------|
| Pulse Strip | 32px flex ticker | 85px grid-cols-3 metric cards | Δh=53px |
| Main Content | Tab 导航 + 2-col grid + actions bar | flex-col 垂直堆叠 | 结构不同 |
| Sidebar | 6 section context rail | 空（sidebar prop 未传） | 完全缺失 |

### Prototype Grid 模型

```
grid-template-areas:
  "rail header   header"
  "rail pulse    pulse"
  "rail main     sidebar"
  "rail status   status";

grid-template-columns: var(--shell-rail-width) 1fr var(--shell-sidebar-width);
grid-template-rows: var(--shell-header-height) auto 1fr auto;
```

### React Audit 数据（2026-04-11）

```
strip:  prototype 56,68,1480x32  |  react 56,68,1480x85.20  |  Δh=53.20
main:   prototype 56,100,1160x752 |  react 56,153,1160x722.80 |  Δy=53.20, Δh=-29.20
sidebar: prototype exists         |  react sidebar = status bar (wrong)
```

## 修复方案

### Step 1: AiPulseStrip → 32px Ticker

重写 `ai-pulse-strip.tsx`：
- 布局：`grid-cols-3 gap-3 p-4` → `flex items-center h-8 px-4 gap-4`
- 内容：三张 Metric card → inline 指标文字 + 分隔符
- 高度：85px → 32px
- 数据源不变（`useAiPulse()`）
- `data-slot` 改为 `pulse-strip`（与 audit config 对齐）

### Step 2: AiContextSidebar 创建

新建 `ai-context-sidebar.tsx`：
- 6 个 context section：AI 运行状态、置信度分布、告警、资源使用、活动时间线、快捷导航
- Mock 数据先行
- `data-slot="sidebar-rail"` 标记
- 样式对齐 prototype context-rail 模式

### Step 3: AiPage Main — Tab 系统

- Tab 导航：Overview / Agents / Copilot / Settings
- `useState` 管理 active tab
- Overview tab：`grid grid-cols-2`（AgentQuickView + CopilotQuickView）+ 4 列 actions bar
- Agents tab：紧凑 agent 列表
- Copilot tab：紧凑 copilot 入口
- Settings tab：AI 配置面板

### Step 4: AiPage 组装

```tsx
<CommandCenterLayout
  pulse={<AiPulseStrip />}          // 32px ticker
  main={<AiMainContent />}          // tab + grid + actions
  sidebar={<AiContextSidebar />}    // context rail
  status={<StatusBar />}            // 24px status bar
/>
```

### Step 5: 验证

- 更新 `ai-components.test.tsx`
- 运行 `bun run visual:audit -- --route /ai`
- L2 偏差 < 2px（strip、main、sidebar、status）
- `bun run check` 通过

## 目标几何（1536x900）

```
ai-shell:  columns 56/1160/320; rows 68/32/752/24
strip:     x=56  y=68  w=1480 h=32
main:      x=56  y=100 w=1160 h=752
sidebar:   x=1216 y=100 w=320  h=752
status:    x=56  y=852 w=1480 h=24
```

## 文件变更

| 文件 | 操作 |
|------|------|
| `src/features/ai/components/ai-pulse-strip.tsx` | 重写 |
| `src/features/ai/components/ai-context-sidebar.tsx` | 新建 |
| `src/features/ai/components/ai-main-content.tsx` | 新建 |
| `src/features/ai/components/ai-page.tsx` | 修改 |
| `src/features/ai/components/ai-components.test.tsx` | 更新 |
| `src/features/ai/index.ts` | 更新 barrel |
