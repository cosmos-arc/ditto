---
paths:
  - "src/styles/design-tokens/*.css"
  - "src/styles/globals.css"
  - "docs/designs/specs/prototypes/page-*.html"
---

# Design Token 架构规范

## 唯一真理源（Single Source of Truth）

> **一份 token 定义，Prototype 和 React 永远使用同一份 CSS 变量值。**

```
src/styles/design-tokens/          ← 唯一真理源
  tokens-base.css                  ← L1: 颜色/间距/字号/圆角/动效/字体
  tokens-semantic.css              ← L2: 表面/文本/边框/品牌
  tokens-shell.css                 ← L3: 壳层布局尺寸
  tokens-data-viz.css              ← L4: 图表/热力图
  tokens-component.css             ← L5: 组件结构
  tokens-interaction.css           ← L6: 交互反馈
  tokens-domain.css                ← L7: 金融域颜色
  tokens-density.css               ← L8: 密度预设
```

## 修改 Token 的唯一流程

```
1. 修改 src/styles/design-tokens/tokens-*.css 中的 :root 值
2. Prototype 自动生效（HTML <link> 直接引用这些文件）
3. React 自动生效（globals.css @import 这些文件 + @theme inline 映射）
4. 运行 bun run check 验证
```

**禁止**：
- 在 `src/styles/globals.css` 的 `@theme inline` 中直接写 oklch 值（必须 `var(--brand-500)` 引用共享 token）
- 在 `docs/designs/specs/prototypes/shared/` 中维护独立 token 文件（已删除）
- 在 `src/styles/tokens/` 中维护独立 token 文件（已删除，由 design-tokens/ 替代）

## 文件格式规则

### 共享 Token 文件（design-tokens/）

全部使用 `:root {}` 定义值：

```css
:root {
  --brand-500: oklch(0.640 0.120 235);
  --font-size-12: 0.75rem;
  --space-16: 1rem;
}
```

### 映射层（globals.css @theme inline）

将 `:root` 变量映射到 Tailwind namespace：

```css
@theme inline {
  --color-brand-500: var(--brand-500);   /* :root → Tailwind */
  --text-sm: var(--font-size-12);         /* :root → Tailwind */
  --spacing-4: 16px;                      /* 具体值（不能用 var(--space-16)） */
}
```

### 兼容别名（globals.css :root）

```css
:root {
  --space-16: 16px;                       /* ✅ 具体值 */
  --row-height: var(--density-row-height); /* ✅ 引用 :root 变量（design-tokens/ 中定义） */
}
```

## `@theme inline` 铁律

**`@theme inline` 中的变量不会生成 `:root` CSS 变量。** 它们只在 Tailwind utility 内部可用。

```css
@theme inline {
  --spacing-4: 16px;    /* Tailwind 内部可用：p-4 = padding: 16px */
}

/* ❌ 运行时 undefined */
:root {
  --my-space: var(--spacing-4);
}
[data-theme="light"] {
  --my-space: var(--spacing-4);
}
```

**判断规则**：
- 变量需要在 `var()` 中被非 Tailwind 代码引用 → 用 `:root {}`
- 变量只通过 Tailwind utility 消费 → 可以用 `@theme inline`

## 命名映射表

### 颜色

| Prototype (`:root`) | Tailwind (`@theme inline`) |
|---|---|
| `--brand-500` | `--color-brand-500` |
| `--neutral-0` | `--color-neutral-0` |
| `--surface-app` | `--color-surface-app` |
| `--text-primary` | `--color-foreground` |
| `--border-subtle` | `--color-border-subtle` |
| `--market-up-fg` | `--color-market-up` / `--color-market-up-fg` |
| `--risk-high-fg` | `--color-risk-high` / `--color-risk-high-fg` |
| `--system-healthy-fg` | `--color-system-healthy` / `--color-system-healthy-fg` |

### 字号

| Prototype | Tailwind | 值 |
|---|---|---|
| `--font-size-10` | `--text-xs` | 10px |
| `--font-size-11` | 无直接映射 | 11px |
| `--font-size-12` | `--text-sm` | 12px |
| `--font-size-13` | `--text-base` | 13px |
| `--font-size-14` | `--text-md` | 14px |
| `--font-size-16` | `--text-lg` | 16px |
| `--font-size-24` | `--text-2xl` | 24px |

**注意**：Prototype 有 7 档核心字号（10/11/12/13/14/16/24）。`text-xl`/`text-3xl`/`text-4xl` 当前与已有档位重复。需要新字号时，先在 `tokens-base.css` 中新增 `:root` 变量。

### 间距

| Prototype | Tailwind | 值 |
|---|---|---|
| `--space-2` | `p-0.5` | 2px |
| `--space-4` | `p-1` | 4px |
| `--space-6` | `p-1.5` | 6px |
| `--space-8` | `p-2` | 8px |
| `--space-10` | `p-2.5` | 10px |
| `--space-12` | `p-3` | 12px |
| `--space-16` | `p-4` | 16px |
| `--space-20` | `p-5` | 20px |
| `--space-24` | `p-6` | 24px |
| `--space-32` | `p-8` | 32px |

### 圆角

| Prototype | Tailwind | 值 |
|---|---|---|
| `--radius-2` | 无直接映射 | 2px |
| `--radius-4` | 无直接映射 | 4px |
| `--radius-6` | `rounded-sm` | 6px |
| `--radius-8` | `rounded-md` | 8px |
| `--radius-12` | `rounded-lg` | 12px |

## 历史踩坑记录

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | `:root` 兼容别名运行时 undefined | `@theme inline` 不生成 `:root` 变量，`var(--spacing-*)` 无效 | 改用具体值 |
| 2 | Prototype ↔ React 颜色漂移 | 两端各自维护独立 token 文件，值不同 | 共享 design-tokens/ SSOT |
| 3 | 字号 text-xl = text-lg | Prototype 只有 6 档字号，9 个 Tailwind 槽位中有 3 个重复 | 文档记录，需要时先在 prototype 新增 |
| 4 | React 组件缺失（Workspace） | L2 bounding rect 通过但模块不存在 | 新增 L0 完整性验证层 |
| 5 | Mock 数据为空导致区域空白 | hook 返回 `[]`，L2 容器高度可能仍通过 | L0 检查 mock 非空 |
| 6 | 间距 token base 不同步 | Prototype 用 4pt base（--space-N），React 用 Tailwind step（--spacing-N） | 映射表固化到此文档 |
