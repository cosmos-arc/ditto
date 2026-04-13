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

/* 3. 共享 Design Tokens（唯一真理源 — :root 变量） */
@import "./design-tokens/tokens-base.css";
@import "./design-tokens/tokens-semantic.css";
/* ... 其余 6 个 token 文件 */

/* 4. @theme inline 映射层（:root → Tailwind namespace） */
/* 注意：这里引用 tokens-*.css 中的 :root 变量是安全的 */
@theme inline {
  --color-brand-500: var(--brand-500);
  --text-sm: var(--font-size-12);
  /* 具体值用硬编码，不能用 var(--spacing-*) 等 @theme inline 内部变量 */
}

/* 5. :root 兼容别名（只能用具体值或 :root 变量，不能用 @theme inline 变量） */
:root {
  --space-16: 16px;  /* ✅ 具体值 */
  --row-height: var(--density-row-height);  /* ✅ 引用 :root 变量（tokens-density.css 中定义） */
}

/* 6. 主题覆盖 */
@import "./themes/dark.css";
@import "./themes/light.css";
@import "./themes/market-intl.css";

/* 7. Base 样式 — 必须在 @layer base 内或使用特定选择器 */
/* ❌ 不要用 * 通配符 reset */

/* 8. 组件样式 — 用 [data-slot] 选择器或放入 @layer components */

/* 9. @keyframes — 无冲突风险，可放在 layer 外 */

/* 10. @media prefers-reduced-motion — 放最后 */
```

## `@theme inline` vs `@theme`

| 特性 | `@theme` | `@theme inline` |
|------|----------|-----------------|
| `:root` 变量 | ✅ 生成 | ❌ **不生成** |
| 注册 utilities | ✅ 是 | ✅ 是 |
| utility 引用方式 | `var(--color-*)` | 直接内联值 |
| 适用场景 | 静态值（颜色、阴影） | 引用其他变量的值 |

### ⚠️ `@theme inline` 铁律：不生成 `:root` 变量

**这是 Tailwind v4 最容易踩的坑。** `@theme inline` 中的变量**只在 Tailwind utility 内部可用**，不会注册为浏览器可访问的 CSS 自定义属性。

```css
@theme inline {
  --spacing-4: 16px;    /* ✅ Tailwind 内部可用：p-4 = padding: 16px */
  --text-sm: 12px;      /* ✅ Tailwind 内部可用：text-sm = font-size: 12px */
}

/* ❌ 致命错误：在 :root 中引用 @theme inline 变量 → undefined */
:root {
  --my-space: var(--spacing-4);    /* ❌ --spacing-4 不存在于 :root，运行时无效 */
  --my-font: var(--text-sm);       /* ❌ --text-sm 不存在于 :root，运行时无效 */
}

/* ✅ 正确：在 :root 中用具体值 */
:root {
  --my-space: 16px;
  --my-font: 12px;
}
```

**判断规则**：
- 如果变量需要在 `var()` 中被**非 Tailwind 代码**（`:root {}`、`[data-theme]`、`globals.css 中的组件样式）引用 → 必须用 `:root {}` 定义
- 如果变量只通过 Tailwind utility class 消费（`p-4`、`text-sm`、`bg-brand-500`）→ 可以用 `@theme inline`

### Token SSOT 架构

```
src/styles/design-tokens/          ← 唯一真理源（Prototype + React 共享）
  tokens-base.css                  ← :root 定义（oklch 值）
  tokens-semantic.css              ← :root 定义
  ...（8 个文件，全部用 :root）

src/styles/globals.css             ← @import 共享 token + @theme inline 映射层
  @import "./design-tokens/tokens-base.css"   ← 导入 :root 变量
  @theme inline {                              ← 映射到 Tailwind namespace
    --color-brand-500: var(--brand-500);       ← Prototype :root → Tailwind utility
    --text-sm: var(--font-size-12);            ← Prototype :root → Tailwind utility
    --spacing-4: 16px;                         ← 具体值（不能用 var(--space-16)，因为 @theme inline 不生成 :root）
  }
```

**修改 token 的唯一入口**：`src/styles/design-tokens/tokens-*.css`。修改后 Prototype 和 React **同时生效**。

### 字号映射规则

Prototype 定义了 6 档字号，Tailwind namespace 暴露 9 个槽位：

| Tailwind utility | Prototype 变量 | 值 | 备注 |
|---|---|---|---|
| `text-xs` | `--font-size-10` | 10px | |
| `text-sm` | `--font-size-12` | 12px | |
| `text-base` | `--font-size-13` | 13px | 注意：非标准 16px |
| `text-md` | `--font-size-14` | 14px | |
| `text-lg` | `--font-size-16` | 16px | |
| `text-xl` | `--font-size-16` | 16px | ⚠️ 与 text-lg 重复 |
| `text-2xl` | `--font-size-24` | 24px | |
| `text-3xl` | `--font-size-24` | 24px | ⚠️ 与 text-2xl 重复 |
| `text-4xl` | `--font-size-24` | 24px | ⚠️ 与 text-2xl 重复 |

**规则**：
- 需要新字号档位（18px/20px/28px）→ 先在 `tokens-base.css` 的 `:root` 中新增 `--font-size-*`，再更新 `@theme inline` 映射
- 禁止在 React 组件中硬编码字号（`text-[18px]`），必须通过 token 体系

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

**Prototype 使用 4pt base scale**，映射到 Tailwind spacing：

| Tailwind | Prototype 变量 | 值 |
|----------|---------------|-----|
| `p-0.5` | `--space-2` | 2px |
| `p-1` | `--space-4` | 4px |
| `p-1.5` | `--space-6` | 6px |
| `p-2` | `--space-8` | 8px |
| `p-2.5` | `--space-10` | 10px |
| `p-3` | `--space-12` | 12px |
| `p-4` | `--space-16` | 16px |
| `p-5` | `--space-20` | 20px |
| `p-6` | `--space-24` | 24px |
| `p-8` | `--space-32` | 32px |

**使用方式**:
```tsx
// ✅ 标准 spacing utilities（优先）
<div className="p-3 py-2 px-4 gap-4 m-2">

// ✅ 引用 density token（组件内部间距）
<div className="p-[var(--density-panel-padding)]">

// ❌ 禁止：硬编码像素值
<div className="p-[16px]">
```

## Design Token 消费模式

```
共享 :root（design-tokens/）→ @theme inline 映射 → Tailwind utility → JSX
```

```css
/* src/styles/design-tokens/tokens-base.css — 唯一真理源 */
:root {
  --brand-500: oklch(0.640 0.120 235);
}

/* src/styles/globals.css — 映射层 */
@theme inline {
  --color-brand-500: var(--brand-500);  /* :root → Tailwind */
}
```

```tsx
/* JSX 中使用 */
<div className="bg-brand-500 text-white" />
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

- **Design Tokens 架构**: [design-tokens.md](design-tokens.md)
- **视觉验证**: [visual-verification.md](visual-verification.md)
- **组件规范**: [components.md](components.md)
