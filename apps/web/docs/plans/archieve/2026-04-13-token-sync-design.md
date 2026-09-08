# Design: Token 同步 + 验证体系升级

> 日期: 2026-04-13
> 状态: Approved
> 目标: 消除 Prototype ↔ React 的 token 不一致根源，升级验证体系覆盖微观样式

## 问题诊断

### 现状

当前 Prototype 和 React 各自维护一套独立的 CSS token 系统：

| 维度 | Prototype | React |
|------|-----------|-------|
| Token 文件 | 8 层 × 14 文件 (docs/) | 8 层 × 8 文件 (src/) |
| Token 数量 | ~200+ 变量 | ~200+ 变量 |
| 命名规范 | `--font-size-13`, `--space-16` | `--text-base`, `--spacing-4` |
| Token 值 | `oklch(0.64 0.12 235)` | `oklch(60% 0.18 235)` |
| CSS 架构 | 零构建、纯 `:root` | Tailwind v4 `@theme inline` |

### 根本原因

两端 token 是**平行独立**的，不是派生关系。转换靠人工记忆 + L2 宏观验证（bounding rect），导致：

1. **颜色漂移**：brand-500、market-up/down 等值两边不同
2. **字号不一致**：Prototype `--font-size-13` vs React `--text-base`，值可能不同
3. **间距偏差**：Prototype `--space-16` vs React `--spacing-4`，映射关系不直观
4. **验证盲区**：L2 审计只检查 8 个大区域的 bounding rect，不检查内部元素的 font-size、font-weight、color、padding

### 业界参考

- **Shopify Polaris**: 独立 `@shopify/polaris-tokens` npm 包，多平台消费
- **GitHub Primer**: `primer/primitives` 仓库，Style Dictionary 编译
- **shadcn/ui + Tailwind v4**: `:root` 定义值 + `@theme inline` 映射到 Tailwind（**最相关**）
- **Tailwind v4 官方**: 推荐同仓库共享 CSS 文件作为 token 唯一真理源

## 设计方案

### 核心原则

> **一份 token 定义，两端消费。Prototype 和 React 永远使用同一份 CSS 变量值。**

### 架构

```
src/styles/
  design-tokens/              ← 新目录：唯一真理源 (Source of Truth)
    tokens-base.css           ← L1: 颜色/间距/字号/圆角/动效
    tokens-semantic.css       ← L2: 表面/文本/边框/品牌
    tokens-shell.css          ← L3: 壳层布局尺寸
    tokens-data-viz.css       ← L4: 图表/热力图
    tokens-component.css      ← L5: 组件结构
    tokens-interaction.css    ← L6: 交互反馈
    tokens-domain.css         ← L7: 金融域颜色
    tokens-density.css        ← L8: 密度预设

  globals.css                 ← @import tailwindcss + @import design-tokens + @theme inline 映射层
  themes/
    dark.css                  ← 保留 (空占位)
    light.css                 ← 保留 ([data-theme="light"] 覆盖)
    market-intl.css           ← 保留 ([data-market-region="intl"] 覆盖)

prototype/
  shared/
    tokens-base.css           ← 删除或改为 @import 重定向
    tokens-semantic.css       ← 删除或改为 @import 重定向
    ...其他 token 文件         ← 删除或改为 @import 重定向
    tokens-style.css          ← 保留 (Style B 个性层)
    layout-base.css           ← 保留 (布局 CSS)
  page-*.html                 ← 改 <link> 引用指向 src/styles/design-tokens/
```

### Token 文件格式

所有 `src/styles/design-tokens/tokens-*.css` 文件使用 `:root` 定义值：

```css
/* src/styles/design-tokens/tokens-base.css */
:root {
  --brand-500: oklch(0.64 0.12 235);
  --font-size-13: 0.8125rem;
  --space-16: 1rem;
  /* ... */
}
```

Prototype 直接消费这些 `:root` 变量。React 通过 `@theme inline` 映射到 Tailwind namespace。

### React globals.css 变更

```css
/* src/styles/globals.css */
@import "tailwindcss";

/* ── 共享 Design Tokens（唯一真理源） ── */
@import "./design-tokens/tokens-base.css";
@import "./design-tokens/tokens-semantic.css";
@import "./design-tokens/tokens-shell.css";
@import "./design-tokens/tokens-data-viz.css";
@import "./design-tokens/tokens-component.css";
@import "./design-tokens/tokens-interaction.css";
@import "./design-tokens/tokens-domain.css";
@import "./design-tokens/tokens-density.css";

/* ── Tailwind v4 Utility 注册层 ── */
/* 将 :root 变量映射到 Tailwind 的 namespace，使 utility classes 可用 */
@theme inline {
  /* 品牌色 */
  --color-brand-500: var(--brand-500);
  --color-brand-400: var(--brand-400);
  --color-brand-300: var(--brand-300);
  --color-brand-600: var(--brand-600);
  --color-brand-700: var(--brand-700);

  /* 中性色 */
  --color-neutral-0: var(--neutral-0);
  --color-neutral-50: var(--neutral-50);
  /* ... */

  /* 字号 */
  --text-xs: var(--font-size-10);
  --text-sm: var(--font-size-12);
  --text-base: var(--font-size-13);
  --text-md: var(--font-size-14);
  --text-lg: var(--font-size-16);
  --text-3xl: var(--font-size-24);

  /* 间距 */
  --spacing-0-5: var(--space-2);
  --spacing-1: var(--space-4);
  --spacing-2: var(--space-8);
  --spacing-3: var(--space-12);
  --spacing-4: var(--space-16);
  /* ... */

  /* 圆角 */
  --radius-sm: var(--radius-4);
  --radius-md: var(--radius-8);
  /* ... */

  /* 字体 */
  --font-body: var(--font-family-ui);
  --font-heading: var(--font-family-heading);
  --font-data: var(--font-family-numeric);
  --font-code: var(--font-family-code);
}
```

### Prototype HTML 变更

将 prototype 的 `<link>` 从引用 `shared/tokens-*.css` 改为引用 `src/styles/design-tokens/tokens-*.css`：

```html
<!-- 旧 -->
<link rel="stylesheet" href="shared/tokens-base.css">
<link rel="stylesheet" href="shared/tokens-semantic.css">

<!-- 新 -->
<link rel="stylesheet" href="../../../src/styles/design-tokens/tokens-base.css">
<link rel="stylesheet" href="../../../src/styles/design-tokens/tokens-semantic.css">
```

### 删除的内容

- `src/styles/tokens/` 目录（01-primitives.css → 08-density.css）— token 定义已迁移到 `src/styles/design-tokens/`
- `prototype/shared/tokens-base.css` 等 — 或改为 `@import` 重定向

### 保留的内容

- `prototype/shared/tokens-style.css` — Style B 个性层，引用共享 token
- `prototype/shared/layout-base.css` — 布局 CSS，消费共享 token
- `prototype/shared/` 中的非 token 文件 — fonts.css、prototype-toggles.css 等
- `src/styles/globals.css` 中的动画、全局样式 — 保持不变
- `src/styles/themes/` — 保持不变
- `src/styles/fonts.css` — 保持不变

## 验证体系升级

### 1. Token Audit 脚本（新增）

`scripts/token-audit.mjs`：

1. 读取 `src/styles/design-tokens/tokens-*.css` 中所有 `:root` 变量定义
2. 读取 `src/styles/globals.css` 中所有 `@theme inline` 映射
3. 验证：
   - 每个 `@theme inline` 变量都有对应的 `:root` 定义
   - 映射的 `var()` 引用了正确的变量名
   - 无孤立变量（:root 中定义但 @theme inline 中未映射的 token）
4. 输出 JSON 报告

### 2. Visual Audit 升级（增强）

`scripts/visual-audit.mjs` 增加 L2.5 微观样式验证：

- 从 prototype 和 React 提取相同选择器的 computed styles
- 对比：font-size、font-weight、color、backgroundColor、padding、gap、border-radius、letterSpacing
- 输出 diff 报告，标记超出阈值的差异
- 每个关键组件（pulse-strip、decision-banner、queue-item、sidebar、secondary-panel）至少检查 3 个子元素

### 3. CI 集成

Token audit 加入 `bun run check`：
```bash
bun run check  # biome + tsc + vitest + token-audit
```

## 迁移步骤

### Phase 1: 创建共享 Token 目录

1. 创建 `src/styles/design-tokens/` 目录
2. 从 `prototype/shared/` 复制 8 个 token 文件到 `src/styles/design-tokens/`
3. 清理复制的文件：移除注释中的 "shared/" 路径引用

### Phase 2: 重写 globals.css

1. 删除 `@import "./tokens/01-primitives"` 等 8 行旧导入
2. 添加 `@import "./design-tokens/tokens-*"` 8 行新导入
3. 在 `@import` 之后添加 `@theme inline` 映射层
4. 保留所有现有全局样式（动画、scrollbar、交互效果等）

### Phase 3: 更新 Prototype 引用

1. 修改所有 prototype HTML 文件的 `<link>` 标签
2. 从 `shared/tokens-*.css` 改为 `../../../src/styles/design-tokens/tokens-*.css`
3. 删除或重定向 prototype 的 `shared/tokens-*.css`

### Phase 4: 清理

1. 删除 `src/styles/tokens/` 目录
2. 删除 prototype 的 `shared/tokens-*.css`（或保留为重定向）
3. 更新兼容别名（`:root` 中的 `--space-*`, `--font-size-*`）

### Phase 5: 验证

1. 运行 token audit 确认同步
2. 运行 visual audit 确认视觉效果
3. 运行 `bun run check` 确认测试/类型/lint 通过
4. 人工视觉对比 prototype vs React

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| Prototype <link> 路径过长 (../../../) | 可用 HTTP 服务器 alias；或 prototype 用相对路径 |
| @theme inline 中 var() 解析问题 | Tailwind v4 的 `inline` 关键字专门解决这个问题 |
| 迁移期间两边不一致 | 分阶段执行，每步后验证 |
| Theme 覆盖可能失效 | themes/ 文件保持不变，它们覆盖的是 :root 变量 |
| 原型文件路径变更影响 CI/CD | visual-audit 脚本路径需要同步更新 |
