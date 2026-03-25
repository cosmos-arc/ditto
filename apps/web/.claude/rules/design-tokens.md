---
paths:
  - "src/styles/**"
---

# Design Token 规范

## 概述

Design Token 是设计系统的原子变量，通过 CSS 变量定义，被 Tailwind CSS 消费。

基于 [Design Token 架构设计](../../docs/designs/2026-03-25-ditto-app-design-token-architecture.md)。

## Token 层级

```
Primitive Token  →  Semantic Token  →  Component Token
  (原始值)            (语义值)           (组件特定值)
```

### Primitive Token

- 直接映射设计稿中的色值
- 命名：`--color-{name}`、`--spacing-{name}`、`--radius-{name}`
- **修改 Primitive Token 需与架构文档同步**

### Semantic Token

- 表达设计意图，引用 Primitive Token
- 命名：`--color-{domain}-{variant}-{usage}`
- **四色域分离**：Market / Risk / System / Signal

```css
/* 示例 */
:root {
  /* System */
  --color-system-background: var(--color-white);
  --color-system-foreground: var(--color-gray-900);

  /* Market */
  --color-market-up: var(--color-green-500);
  --color-market-down: var(--color-red-500);

  /* Risk */
  --color-risk-low: var(--color-green-500);
  --color-risk-high: var(--color-red-500);

  /* Signal */
  --color-signal-buy: var(--color-green-500);
  --color-signal-sell: var(--color-red-500);
}
```

## 色彩空间约束

- 使用 **OKLCH** 色彩空间
- 禁止使用 HEX / RGB / HSL 定义新 Token

```css
/* ✅ 正确 */
--color-primary: oklch(0.7 0.15 250);

/* ❌ 禁止 */
--color-primary: #3b82f6;
```

## 图表颜色

图表使用独立颜色体系，不受 Semantic Token 约束：

```css
--color-chart-1: oklch(0.7 0.15 250);
--color-chart-2: oklch(0.6 0.18 160);
/* ... */
```

## 暗色/亮色映射

每个 Semantic Token 必须同时定义亮色和暗色值：

```css
:root {
  --color-system-background: oklch(1 0 0);
}

.dark {
  --color-system-background: oklch(0.15 0 0);
}
```

**检查清单**：
- [ ] 新增 Token 是否同时定义了亮色和暗色？
- [ ] 命名是否遵循 `{domain}-{variant}-{usage}` 模式？
- [ ] 是否使用了 OKLCH 色彩空间？
