---
paths:
  - "src/**/*.css"
  - "src/**/*.tsx"
---

# Tailwind CSS 规范

## 配置方式

使用 **Tailwind CSS v4 CSS-first 配置**，在 `src/styles/globals.css` 中通过 `@theme` 定义。

## 核心规则

### 禁止 inline styles

```tsx
// ❌ 禁止
<div style={{ color: "red", fontSize: "16px" }} />

// ✅ 正确
<div className="text-red-500 text-base" />
```

### @apply 使用限制

`@apply` 仅限以下场景使用：
- `src/styles/globals.css`（全局样式）
- shadcn/ui 组件内部

```css
/* ✅ 允许：globals.css */
@layer base {
  h1 {
    @apply text-2xl font-bold;
  }
}

/* ❌ 禁止：业务组件中使用 @apply */
/* 直接在 JSX 中使用 utility classes */
```

## Design Token 消费模式

CSS 变量 → Tailwind utility → JSX

```css
/* src/styles/globals.css — 定义 Token */
@theme inline {
  --color-primary: oklch(0.7 0.15 250);
}
```

```tsx
/* JSX 中使用 */
<div className="bg-primary text-white" />
```

## 响应式断点约定

使用 Tailwind 默认断点，不自定义：

| 断点 | 宽度 | 用途 |
|------|------|------|
| `sm` | ≥ 640px | 移动端横屏 |
| `md` | ≥ 768px | 平板 |
| `lg` | ≥ 1024px | 桌面 |
| `xl` | ≥ 1280px | 大屏 |
| `2xl` | ≥ 1536px | 超大屏 |

**原则**：Mobile First — 默认样式为移动端，使用 `md:` / `lg:` 向上扩展。

## 暗色/亮色主题切换

使用 CSS 变量 + `dark:` variant 实现。

```css
/* globals.css — Ditto 使用 @theme inline 桥接 + :root/.dark 变量切换 */
@custom-variant dark (&:is(.dark *));

@theme inline {
  --color-background: var(--color-surface-app);
  --color-foreground: var(--color-text-primary);
}

:root {
  --color-surface-app: oklch(1 0 0);
  --color-text-primary: oklch(0.15 0 0);
}

.dark {
  --color-surface-app: oklch(0.15 0 0);
  --color-text-primary: oklch(0.95 0 0);
}
```

## 相关规范

- **Design Tokens**: [design-tokens.md](design-tokens.md)
- **组件规范**: [components.md](components.md)
