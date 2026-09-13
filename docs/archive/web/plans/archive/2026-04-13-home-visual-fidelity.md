# Home 页面视觉还原 — 综合修复方案

## Context

当前 home 页面 L3 像素对比 diff ratio 为 7.64%（阈值 2%），肉眼可见显著差异。
根因不是布局问题（L2 完美），而是 **视觉效果的系统性遗漏** + **字体加载不一致**。

调研结论：业界最佳实践是 "design intent matching"（匹配设计意图），方法是通过 computed style 逐属性对比 + 人眼 side-by-side 验证，而非纯像素计数。

参考：
- [Rethinking Pixel Perfect (Smashing Magazine)](https://www.smashingmagazine.com/2026/01/rethinking-pixel-perfect-web-design/)
- [Chasing the Pixel-Perfect Dream (Josh Comeau)](https://www.joshwcomeau.com/css/pixel-perfection/)

---

## Step 1: 修复字体加载（消除最大干扰变量 ~3% diff）

**问题**: Google Fonts 在本地开发环境超时 → 两侧 fallback 到不同字体 → 抗锯齿完全不同

**具体差异**:
- Prototype 加载 3 个 Google Fonts: Inter, Noto Sans SC, JetBrains Mono
- React 加载 5 个 Google Fonts (多了 IBM Plex Sans/Mono, Material Symbols) + Geist Sans/Mono (Fontsource) + Noto Sans SC (bundled)
- React heading 用 **Geist Sans**，prototype 根本没加载 Geist
- Noto Sans SC: React `display: optional` vs prototype `display: swap`

**修复方案**: 让 prototype 和 React 使用完全相同的字体栈

1. **prototype HTML**: 添加 Geist 字体加载（与 React 一致），确保 heading 字体匹配
2. **React**: 确认 Geist Sans/Mono 通过 Fontsource 正确加载（已做）
3. **两侧统一**: 确保 Inter 作为 body 字体、JetBrains Mono 作为 data 字体在两侧一致
4. **临时方案**: 如果 Google Fonts 仍超时，在 Playwright 截图前等待 `document.fonts.ready` + 额外等待确保字体加载

**涉及文件**:
- `prototype/page-home.html` (第 33-36 行 `<link>` 标签)
- `prototype/shared/layout-base.css` (第 72-74 行 `--font-family-*`)
- `prototype/shared/tokens-base.css` (token 引用)

---

## Step 2: 扩展 visual-audit 工具提取视觉属性

**问题**: 当前 `visual-audit-core.mjs` 只提取 `backgroundColor` 等 13 个布局属性，**完全遗漏**所有视觉效果属性

**需新增提取的 computed style 属性**:
```
boxShadow, backdropFilter, WebkitBackdropFilter,
borderColor, borderLeftColor, borderBottomColor, borderStyle,
opacity, background, backgroundImage,
filter, fontFamily, fontWeight, fontSize, letterSpacing,
fontFeatureSettings, transform, zIndex,
textRendering, WebkitFontSmoothing
```

**需新增**: 伪元素 `::before` / `::after` 的 computed style 提取（用 `window.getComputedStyle(el, '::before')`）

**涉及文件**:
- `scripts/visual-audit-core.mjs` (STYLE_PROPS 数组)
- `scripts/visual-audit.config.mjs` (可能需要新增选择器)

---

## Step 3: 修复已确认的视觉差异（逐项）

基于两个 Explore agent 的完整 CSS 清单，以下是 React 缺失或错误的视觉效果:

### 3.1 Header 背景透明度
- **Prototype**: `background: var(--surface-frosted)` → `oklch(from var(--surface-app) l c h / 0.85)`
- **React**: `--color-surface-frosted` = `oklch(0.155 0.005 253 / 0.8)`
- **修复**: 将 token 值从 `0.8` 改为 `0.85`
- **文件**: `src/styles/tokens/02-semantic.css`

### 3.2 Context section hover 双重效果
- **Prototype**: 仅 `background: color-mix(in oklch, var(--brand-accent) 2%, var(--surface-card))`
- **React**: globals.css 有 `box-shadow: inset 0 0 0 1px ...` + 组件有 `hover:bg-[color-mix(...)]` → **双重效果**
- **修复**: 移除 globals.css 中的 `[data-slot="context-section"]:hover` inset box-shadow
- **文件**: `src/styles/globals.css` (约 172-177 行)

### 3.3 Secondary panel hover
- **Prototype**: `transition: border-color ..., box-shadow ...; hover { border-color: accent 10%; box-shadow: 0 1px 4px -1px accent 4% }`
- **React**: `home-secondary` div 无 hover 效果
- **修复**: 添加 CSS transition + hover 状态到 `[data-slot="home-secondary"] > *` 或直接在 `globals.css`
- **文件**: `src/styles/globals.css`

### 3.4 Queue item priority bar micro-glow
- **Prototype**: `.queue-item:hover .queue-item-bar.p1 { box-shadow: 0 0 6px 1px risk-high 20% }`
- **React**: priority bar 仅纯色条，无 hover glow
- **修复**: 在 `globals.css` 添加 hover 状态
- **文件**: `src/styles/globals.css`, `src/features/home/components/priority-queue-section.tsx`

### 3.5 Context section separator
- **Prototype**: `::before` 伪元素 + `background: var(--overlay-3)` (3% 白色透明度)
- **React**: `home-page.tsx` 用 `border-t border-(--color-border-subtle)` (实线边框)
- **修复**: 移除 `border-t`，改用 CSS `::before` 实现 overlay-3 效果
- **文件**: `src/features/home/components/home-page.tsx`, `src/styles/globals.css`

### 3.6 Regime tag hover glow
- **Prototype**: `box-shadow: 0 0 0 1px color-mix(in oklch, var(--text-secondary) 12%, transparent)`
- **React**: 缺失
- **修复**: 添加到相关组件
- **文件**: 搜索 regime-tag 相关组件

### 3.7 NoiseLayer z-index
- **Prototype**: `.noise-layer { z-index: 0 }`，ambient bars 分别 z-index: 2/5
- **React**: `z-50` 在容器上，会盖住所有内容
- **修复**: 降低 z-index
- **文件**: `src/features/shell/components/noise-layer.tsx`

### 3.8 Decision CTA active state
- **Prototype**: `transform: scale(0.97)` 按下微缩放
- **React**: shadcn Button 基础类有 `active:translate-y-px`，可能不同
- **验证**: 检查 DecisionBanner 按钮的 active 状态

### 3.9 Header accent line 简化
- **Prototype**: 5-stop gradient (15% → 25% → 15%)
- **React**: 3-stop via-gradient (25% midpoint)
- **修复**: 更新为匹配原型的 5-stop gradient
- **文件**: `src/features/shell/components/header.tsx`

### 3.10 Light mode 调整
- **Prototype**: ambient bars opacity 0.4, noise layer opacity 0.008, main-primary glow opacity 0.3
- **React**: 缺失 light mode 覆盖
- **修复**: 添加 light mode CSS 规则
- **文件**: `src/styles/globals.css` 或 `src/styles/themes/light.css`

---

## Step 4: 运行完整视觉验证

修复完成后:
1. 重启 dev server + prototype server
2. 用 Playwright 统一截图（`channel: 'chromium'`, `viewport: 1536x900`）
3. 逐区域人眼对比（不是像素计数）
4. 如果仍有明显差异，回到 Step 3 继续修复

---

## 验证标准

- `bun run check` 通过
- 人眼 side-by-side 对比无明显视觉差异
- L3 diff ratio 显著下降（预期 < 3%）
