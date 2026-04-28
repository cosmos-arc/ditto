# Ditto Shell Chrome Contract

> **版本**：v1.0
> **日期**：2026-04-28
> **状态**：Draft
> **上游**：[01 产品信息架构](./01_product_information_architecture.md)、[10 Shell Family 规范](./10_ditto_shell_family_spec.md)
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
| Global Utilities | command、Copilot、notifications、help、account | workspace 执行动作 |

全局工具顺序固定：

1. Global Command
2. Copilot
3. Notifications
4. Help
5. Account / View Preferences

## 4. Search Scope

搜索必须显式标注作用域。

| 作用域 | 属性 | 位置 |
|---|---|---|
| Global command/search | `data-shell-utility="command"` + `data-search-scope="global"` | Header |
| Workspace filter/search | `data-workspace-action="filter"` | Workspace toolbar |
| Table search | `data-table-toolbar="search"` | Data surface |

同一个视觉组件可以复用，但不能复用模糊语义。

## 5. View Preferences

Theme 与 density 是视图偏好，不是常驻 Header segmented controls，也不是 Rail 控件。

Prototype 必须使用：

```html
<button data-shell-utility="account">...</button>
<div data-view-preferences-menu>
  <button data-set-density="dense">...</button>
  <button data-set-theme="light">...</button>
</div>
```

React 必须映射为：

```tsx
<HeaderUtilityBar>
  <GlobalCommandButton />
  <CopilotButton />
  <NotificationsButton />
  <HelpButton />
  <ViewPreferencesMenu />
</HeaderUtilityBar>
```

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
| Account/preferences | `data-shell-utility="account"` | Header | Account + view prefs |
| View preferences menu | `data-view-preferences-menu` | Account menu | Theme/density only here |
| Workspace toolbar | `data-workspace-toolbar` | Page shell | Page-level actions |
| Table toolbar | `data-table-toolbar` | Data surface | Search/filter/bulk/columns |

## 8. React Mapping

| Contract Slot | React Component |
|---|---|
| Page Identity | `PageTitleBlock` |
| Header Utility Bar | `HeaderUtilityBar` |
| Global command | `GlobalCommandButton` |
| Account/preferences | `ViewPreferencesMenu` |
| Data-local actions | `DataToolbar` |

Shell Family 差异从全局 Rail 与 Header Utility Bar 之下开始。
