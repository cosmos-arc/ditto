# Ditto Shell Chrome Contract

> **版本**：v1.0
> **日期**：2026-04-28
> **状态**：Draft
> **上游**：[01 产品信息架构](01_product_information_architecture.md)、[10 Shell Family 规范](10_ditto_shell_family_spec.md)
> **下游**：Prototype HTML、Page Contract、React Shell Components、Guardrail Tests
> **职责**：定义全局 Rail、Header、搜索、视图偏好、账号入口与本地工具栏的统一合同

## 1. 目标

Shell Chrome Contract 位于具体 Shell Family 之上。
它约束所有页面共享的全局 chrome 语法，确保 prototype、page contract 与 React 实现使用同一套 `data-*` 语义。

合同范围包括：

- 全局 Rail
- 全局 Header 左中右区域
- Header Utility Bar
- 搜索作用域
- 视图偏好入口
- Workspace Toolbar 与 Data Toolbar 的动作边界
- Prototype 与 React 的属性映射

## 2. Rail

Rail 只承担五个一级产品域导航：

- Home
- Markets
- Research
- Trading
- Platform

Rail 不承载：

- theme / density
- account / user
- settings
- notifications
- table filter / export / refresh / columns
- workspace 内部动作

每个域链接必须暴露：

```html
data-rail-domain="{domain}"
```

`domain` 只能是 `home`、`markets`、`research`、`trading`、`platform`。

## 3. Header

Header 从左到右承担三段稳定职责：

| 区域 | 职责 | 不允许 |
|---|---|---|
| Page Identity | 页面标题、可选副标题、domain/scope/session metadata | 表格筛选、导出、列配置 |
| Context Spacer | 轻量上下文、状态摘要、留白 | filter workbench |
| Global Utilities | command、Copilot、notifications、help、theme、density、account | workspace 执行动作 |

全局工具顺序固定：

1. Global Command
2. Copilot
3. Notifications
4. Help
5. Theme
6. Density
7. Account

## 4. Search Scope

搜索必须显式标注作用域。

| 作用域 | 属性 | 位置 |
|---|---|---|
| Global command/search | `data-shell-utility="command"` + `data-search-scope="global"` | Header |
| Workspace filter/search | `data-workspace-action="filter"` | Workspace toolbar |
| Table search | `data-table-toolbar="search"` | Data surface |

同一个视觉组件可以复用，但不能复用模糊语义。

## 5. View Preferences

Theme 与 density 是视图偏好。它们可以常驻 Header，但只能以 icon-only toggle 出现；不得使用弹窗、segmented controls 或 Rail 控件。

Prototype 必须使用：

```html
<button id="theme-toggle" data-shell-utility="theme">...</button>
<button id="density-toggle" data-shell-utility="density">...</button>
<button data-shell-utility="account">...</button>
```

React 必须映射为：

```tsx
<HeaderUtilityBar>
  <GlobalCommandButton />
  <CopilotButton />
  <NotificationsButton />
  <HelpButton />
  <ThemeToggleButton />
  <DensityToggleButton />
  <AccountButton />
</HeaderUtilityBar>
```

### 5.1 Theme / Density Toggle Refinement（2026-04-29）

业界参考：Fluent 2 Popover/Menu、Carbon UI Shell/Modal、GitHub Primer ActionMenu/Dialog、SAP Fiori Content Density。

本项目采用以下收敛规则：

- Header 暴露两个直接 icon toggle：`theme-toggle` 与 `density-toggle`；不再使用 view preferences popover。
- Theme toggle 在 `dark ↔ light` 间切换，Density toggle 在 `compact → comfortable → dense` 间循环。
- Toggle 必须只用图标、`aria-label` 与 `title` 表达当前状态，不展示说明性 hint 或弹窗内容。
- 密度切换必须映射到密度 token，不为单个页面或单个组件写独立间距补丁。
- Header chrome 的底色、边线、间距、utility 顺序由 shared layout 控制；单页不得用 frosted header、渐变分隔线或独立 Header 光效制造差异。
- Page title 使用一致语言风格，禁止单页标题使用英文营销名；标题下划线和渐变标题装饰统一关闭。
- Overlay surface 使用 shared overlay grammar：同一 surface token、同一边框/圆角；单页只定义内容语义，不重新定义弹层外壳或重阴影。

## 6. Workspace And Data Toolbars

本地动作不得伪装成全局 shell utility。
该矩阵是 Page Pattern、Data Views、Prototype 与 React 实现共享的动作放置规则。

| 动作 | 放置 |
|---|---|
| Global command/search | Header utility |
| Copilot | Header utility |
| Notifications | Header utility |
| Help | Header utility |
| Account/view preferences | Header utility |
| Export table | Data toolbar |
| Refresh table | Data toolbar or workspace toolbar |
| Filter table/list | Data toolbar |
| Column configuration | Data toolbar |
| Run backtest / execute screening | Workspace toolbar |
| Save/publish strategy | Studio header or workspace toolbar |
| Settings/config validation | Config workspace toolbar |

## 7. Required Attributes

| Slot | Required Attribute | Owner | Notes |
|---|---|---|---|
| Rail domain link | `data-rail-domain="{domain}"` | Rail | Five IA domains only |
| Global command | `data-shell-utility="command"` | Header | Opens global command/search |
| Copilot | `data-shell-utility="copilot"` | Header | Opens global sidecar |
| Notifications | `data-shell-utility="notifications"` | Header | Global alerts only |
| Help | `data-shell-utility="help"` | Header | Product help |
| Theme toggle | `id="theme-toggle"` + `data-shell-utility="theme"` | Header | Direct icon toggle |
| Density toggle | `id="density-toggle"` + `data-shell-utility="density"` | Header | Direct icon toggle |
| Account | `data-shell-utility="account"` | Header | Account entry only |
| Workspace toolbar | `data-workspace-toolbar` | Page shell | Page-level actions |
| Table toolbar | `data-table-toolbar` | Data surface | Search/filter/bulk/columns |

## 8. React Mapping

| Contract Slot | React Component |
|---|---|
| Page Identity | `PageTitleBlock` |
| Header Utility Bar | `HeaderUtilityBar` |
| Global command | `GlobalCommandButton` |
| Theme toggle | `ThemeToggleButton` |
| Density toggle | `DensityToggleButton` |
| Account | `AccountButton` |
| Data-local actions | `DataToolbar` |

Shell Family 差异从全局 Rail 与 Header Utility Bar 之下开始。

## 9. Command Discoverability Addendum（2026-04-29）

全局 Command 入口可以保持 icon-only，但必须在机器合同和用户可发现性上显式：

```html
<button
  data-shell-utility="command"
  data-search-scope="global"
  data-command-scope="global"
  aria-label="打开全局命令 Ctrl+K"
  title="打开全局命令 Ctrl+K"
></button>
```

本地搜索不得复用全局命令语义：

- Workspace filter 使用 `data-workspace-action="filter"`。
- Table / list search 使用 `data-local-search`。
- 全局入口使用 `data-command-scope="global"`。

评分和门禁应把“本地搜索误标为全局 command”视为 Chrome 合同错误。

## 10. Expert Efficiency Contract

专家入口页必须显式暴露：

- 5 秒主答案：`data-primary-answer`。
- 选中对象联动区域：至少两个 `data-selected-object-region`。
- Studio / Agent React parity 槽位：`main`、`sidebar`、`inspector` 或 `detail`、`activity-log`、`status`。
- 关键状态的非颜色表达：`data-critical-status` 内必须有 `data-danger-marker` 或 `data-status-label`。

这组合同用于防止高分原型只在视觉上完成，而没有把专家工作流效率落实到结构里。
