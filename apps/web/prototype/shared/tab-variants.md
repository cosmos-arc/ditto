# Tab 变体使用规则

> 两种 tab 样式变体在 Prototype 中的使用规则和 CSS 类名映射。

## Pill Tab

**用途**: Dashboard 布局页面（Home, Trading Overview, Portfolio）

**特征**: 圆角药丸状背景，选中态有填充色背景

**CSS 类名**:
- 容器: `.tab-bar` 或 `.pill-tabs`
- 选项: `.tab-radio` + `.tab-label` (radio toggle)
- 选中态: `.tab-radio:checked + .tab-label`

**使用页面**:
- `page-home.html` — 概览/策略/交易 tab
- `page-trading-overview.html` — 交易模式/复核模式 tab
- `page-portfolio.html` — 组合/归因/风控 tab

## Underline Tab

**用途**: IDE 布局页面（Agent Console）

**特征**: 底部边框指示器，无背景填充，更紧凑

**CSS 类名**:
- 容器: `.ide-tabs` 或 `.underline-tabs`
- 选项: `.ide-tab` + `:checked` 态
- 指示器: `::after` bottom border

**使用页面**:
- `page-agent-console-v2.html` — Findings/Auto Research/Tools tab

## 决策规则

| 页面类型 | Tab 变体 | 原因 |
|---------|---------|------|
| Dashboard（三栏布局） | Pill Tab | 视觉密度较低，pill 提供更好的可点击区域 |
| IDE（多面板布局） | Underline Tab | 面板内空间有限，underline 更节省空间 |
| 列表页（目录布局） | 不使用 tab | 列表页使用 filter bar 而非 tab |

## 共享样式位置

所有 tab 样式定义在 `shared/layout-components.css` 中搜索 `.tab-` 或 `.ide-tab` 前缀。
