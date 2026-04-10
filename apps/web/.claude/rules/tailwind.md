---
paths:
  - "src/**/*.css"
  - "src/**/*.tsx"
---

# Tailwind CSS v4 规范

## 配置方式

使用 **Tailwind CSS v4 CSS-first 配置**，无 `tailwind.config.js`。所有配置通过 CSS `@theme` 完成。

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

## CSS Cascade Layers — 关键规则

**Tailwind v4 的层优先级**（从低到高）：

```
@layer theme → @layer base → @layer components → @layer utilities → unlayered CSS
```

### ❌ 绝对禁止：在 `@layer` 外写 reset

**Unlayered CSS 优先级高于所有 `@layer`**，会覆盖所有 utility classes。

```css
/* ❌ 致命错误：* { padding: 0 } 在 layer 外，覆盖所有 p-*, py-*, px-*, gap-* */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* ✅ Tailwind v4 Preflight 已包含完整 reset，无需自定义 */
/* 如确需自定义 base 样式，必须放在 @layer base 内 */
@layer base {
  html { -webkit-font-smoothing: antialiased; }
}
```

**Why**: 之前因 `@layer base { * { padding: 0 } }` 被 Tailwind 处理后变成 unlayered CSS，
导致所有 spacing utilities（p-3, py-3, px-4 等）失效。

### globals.css 组织顺序

```css
/* 1. 导入 Tailwind（建立 cascade layers） */
@import "tailwindcss";

/* 2. 自定义变体 */
@custom-variant dark (&:is(.dark *));

/* 3. Token 文件（@theme 定义） */
@import "./tokens/01-primitives.css";

/* 4. 主题覆盖 */
@import "./themes/dark.css";

/* 5. Base 样式 — 必须在 @layer base 内或使用特定选择器 */
/* ❌ 不要用 * 通配符 reset */

/* 6. 组件样式 — 用 [data-slot] 选择器或放入 @layer components */

/* 7. @keyframes — 无冲突风险，可放在 layer 外 */

/* 8. @media prefers-reduced-motion — 放最后 */
```

## `@theme inline` vs `@theme`

| 特性 | `@theme` | `@theme inline` |
|------|----------|-----------------|
| `:root` 变量 | ✅ 生成 | ❌ 不生成 |
| 注册 utilities | ✅ 是 | ✅ 是 |
| utility 引用方式 | `var(--color-*)` | 直接内联值 |
| 适用场景 | 静态值（颜色、阴影） | 引用其他变量的值 |

```css
/* 静态颜色 → 普通 @theme */
@theme {
  --color-brand-500: oklch(0.55 0.2 235);
  /* 生成 :root { --color-brand-500: ... } + .bg-brand-500 { background: var(--color-brand-500) } */
}

/* 引用其他变量 → inline */
@theme inline {
  --font-sans: var(--font-body);
  /* 生成 .font-sans { font-family: var(--font-body) } — 不生成 :root 变量 */
}

/* Spacing 步进覆盖 → inline（避免 calc(var * N) 被固定值覆盖） */
@theme inline {
  --spacing-3: 12px;  /* .p-3 生成 padding: 12px 而非 calc(var(--spacing) * 3) */
}
```

## `text-*` 歧义解决

`text-` 命名空间同时用于字号和颜色。CSS 变量引用时 Tailwind 无法自动判断类型。

```tsx
// ❌ text-(--font-size-14) 被解析为颜色（无效）
<span className="text-(--font-size-14)">

// ✅ 使用命名 utility
<span className="text-sm">           // 12px（来自 --text-sm）
<span className="text-base">         // 13px（来自 --text-base）
<span className="text-md">           // 14px（来自 --text-md）
<span className="text-lg">           // 18px（来自 --text-lg）

// ✅ 必须用 CSS 变量时，加 length 类型提示
<span className="text-(length:--text-md)">

// ✅ 引用颜色变量不需要提示（text- 默认解析为 color）
<span className="text-(--color-accent)">
```

## Spacing Utilities

**基础变量**: `--spacing: 0.25rem`（4px），所有 spacing 用 `calc(var(--spacing) * N)` 生成。

**步进覆盖**（在 `@theme inline` 中定义）:
```css
@theme inline {
  --spacing-0-5: 2px;
  --spacing-1: 4px;
  --spacing-2: 8px;
  --spacing-3: 12px;  /* p-3 = 12px 而非 calc(0.25rem * 3) = 12px（巧合一致） */
  --spacing-4: 16px;
}
```

**使用方式**:
```tsx
// ✅ 标准 spacing utilities
<div className="p-3 py-2 px-4 gap-4 m-2">

// ✅ 使用 design token 变量
<div className="p-[var(--spacing-3)]">

// ✅ 构建时 spacing 函数（在 CSS 中）
.card { padding: --spacing(4); }
```

## Design Token 消费模式

CSS 变量 → Tailwind utility → JSX

```css
/* src/styles/tokens/ — 定义 Token */
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
@custom-variant dark (&:is(.dark *));

@theme inline {
  --color-background: var(--color-surface-app);
  --color-foreground: var(--color-text-primary);
}

:root {
  --color-surface-app: oklch(1 0 0);
}
.dark {
  --color-surface-app: oklch(0.15 0 0);
}
```

## 内容检测（v4 自动扫描）

Tailwind v4 **自动检测**项目文件中的 class 名，无需 `content` 配置。

- 自动扫描所有源文件（排除 `.gitignore`、`node_modules`、二进制文件）
- 使用 `@source` 指令添加/排除路径：
  ```css
  @source "../packages/ui";           /* 添加扫描路径 */
  @source not "../src/legacy";        /* 排除路径 */
  @source inline("underline");        /* 强制生成特定 utility */
  ```
- 与 Vite 集成时通过文件系统扫描，不依赖 Vite 模块图

## 相关规范

- **Design Tokens**: [design-tokens.md](design-tokens.md)
- **组件规范**: [components.md](components.md)
