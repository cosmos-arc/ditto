# Living Graphite — 设计系统增强方案

> **状态**：✅ 已完成（2026-04-24）
> **分支**：`feat/prototype-three-zone-architecture`
> **验证**：biome ✅ | tsc ✅ (仅预存错误) | vitest 97/1136 ✅ | 原型 29/29 ✅

## Context

量化交易平台 Ditto 的设计系统在工程层面已经很完善（8 层 oklch token、30 个 HTML 原型、完整的 Domain 色彩语义），但存在四个系统性痛点：

1. **视觉单调** — 所有页面共享同一套 brass signature，没有 Domain 身份辨识度
2. **信息层次不清** — text-primary/tertiary 对比比仅 1.67:1，信息密集时关键数据不突出
3. **缺少专业工具感** — 面板层级扁平，缺少"精密仪器"的质感
4. **长时间疲劳** — 界面完全静态，从开盘到收盘同一张面孔

本方案以现有 token 体系和原型为唯一准绳，通过三个支柱做**增量增强**，不替换现有设计。

---

## 三支柱总览

| 支柱 | 核心思路 | 解决的痛点 |
|------|---------|-----------|
| **Chromatic Atmosphere** | 背景色温随时间/市场状态做亚感知级渐变 | 疲劳 + 单调 |
| **Contextual Identity** | 每个 Domain 有独立的签名色，自动流入三个"光点" | 单调 + 专业感 |
| **Signal Amplification** | 文本对比度增强 + 方向性数值光晕 + Metric Hero 模式 | 信息层次 + 专业感 |

---

## 实施阶段

用户要求：**先更新规范和 token/视觉层，再统一更新所有原型**。因此分两大阶段：

- **阶段 A（规范 + Token + CSS + React Hook）**：更新设计系统规范和代码，建立 Living Graphite 的完整基础设施
- **阶段 B（原型同步）**：在阶段 A 验证通过后，统一更新 30 个 HTML 原型

---

### 阶段 A: 规范与代码实施

### Batch 1: Token 层基础（非视觉，无风险）

#### Step 1: 新建 `src/styles/design-tokens/tokens-atmosphere.css`

新文件，定义亚感知级氛围变量。默认值为零（无 JS 运行时 = 当前行为不变）。

```css
:root {
  --atmosphere-hue-shift: 0;       /* ±7 degrees, JS hook 设置 */
  --atmosphere-chroma-boost: 0;    /* ±0.002 */
  --atmosphere-lightness-shift: 0; /* ±0.003 */
  --atmosphere-breathe-duration: 45s;

  --surface-app-atmosphere: oklch(
    calc(0.166 + var(--atmosphere-lightness-shift))
    calc(0.010 + var(--atmosphere-chroma-boost))
    calc(253 + var(--atmosphere-hue-shift))
  );
}
[data-theme="light"] {
  --surface-app-atmosphere: oklch(
    calc(0.988 + var(--atmosphere-lightness-shift))
    calc(0.001 + var(--atmosphere-chroma-boost))
    calc(253 + var(--atmosphere-hue-shift))
  );
}
```

**注意**：需先验证 `oklch(calc(...))` 在目标浏览器中的支持情况（Chrome 111+, Firefox 128+, Safari 16.4+）。若不支持，回退方案为预计算 4 个离散 surface 值（pre-market/active/post-market/closed）由 JS 直接切换。

#### Step 2: 文本对比度增强 — `src/styles/design-tokens/tokens-semantic.css`

仅改 2 个值（第 29、31 行）：

| Token | 当前值 | 新值 | 变化 |
|-------|--------|------|------|
| `--text-primary` | `oklch(0.925 0.004 253)` | `oklch(0.940 0.004 253)` | L +0.015 |
| `--text-tertiary` | `oklch(0.555 0.007 253)` | `oklch(0.480 0.007 253)` | L -0.075 |

对比比从 1.67:1 提升到 ~1.96:1。亮色模式对应值（第 118、120 行）同理微调：
- `--text-primary`: `oklch(0.155 ...)` → `oklch(0.140 0.015 253)`（更深）
- `--text-tertiary`: `oklch(0.550 ...)` → `oklch(0.490 0.010 253)`（更浅）

#### Step 3: Domain 签名色覆盖 — `src/styles/design-tokens/tokens-semantic.css`

在 `:root {}` 结束（第 98 行）后、`[data-theme="light"]` 之前插入：

```css
[data-domain="trading"] {
  --brand-signature-fg:     oklch(0.760 0.055 74);   /* Brass — 当前默认 */
  --brand-signature-muted:  oklch(0.660 0.040 74);
  --brand-signature-line:   oklch(0.620 0.040 74);
  --brand-signature-subtle: oklch(0.760 0.055 74 / 0.08);
}
[data-domain="markets"] {
  --brand-signature-fg:     oklch(0.731 0.095 220);   /* Cyan — 冷静观察 */
  --brand-signature-muted:  oklch(0.631 0.070 220);
  --brand-signature-line:   oklch(0.580 0.065 220);
  --brand-signature-subtle: oklch(0.731 0.095 220 / 0.08);
}
[data-domain="research"] {
  --brand-signature-fg:     oklch(0.732 0.095 300);   /* Purple — 思考探索 */
  --brand-signature-muted:  oklch(0.632 0.070 300);
  --brand-signature-line:   oklch(0.582 0.065 300);
  --brand-signature-subtle: oklch(0.732 0.095 300 / 0.08);
}
[data-domain="platform"] {
  --brand-signature-fg:     oklch(0.640 0.100 235);   /* Lapis — 秩序控制 */
  --brand-signature-muted:  oklch(0.540 0.080 235);
  --brand-signature-line:   oklch(0.470 0.070 235);
  --brand-signature-subtle: oklch(0.640 0.100 235 / 0.08);
}
[data-domain="home"] {
  --brand-signature-fg:     oklch(0.760 0.055 74);   /* Brass — 温暖首页 */
  --brand-signature-muted:  oklch(0.660 0.040 74);
  --brand-signature-line:   oklch(0.620 0.040 74);
  --brand-signature-subtle: oklch(0.760 0.055 74 / 0.08);
}
[data-domain="ai"] {
  --brand-signature-fg:     oklch(0.680 0.110 310);   /* Magenta — 智能创造 */
  --brand-signature-muted:  oklch(0.580 0.085 310);
  --brand-signature-line:   oklch(0.510 0.075 310);
  --brand-signature-subtle: oklch(0.680 0.110 310 / 0.08);
}
```

亮色模式对应值在 `[data-theme="light"]` 块末尾添加 `[data-theme="light"][data-domain="X"]` 复合选择器，每个 Domain 的 L 值下调 ~0.24，chroma 略降。

---

### Batch 2: 连接层（将 token 连接到运行时）

#### Step 4: 导入 atmosphere — `src/styles/globals.css`

在第 11 行 `@import "./design-tokens/tokens-semantic.css"` 后插入：
```css
@import "./design-tokens/tokens-atmosphere.css";
```

#### Step 5: Surface-app 接入 atmosphere — `tokens-semantic.css`

第 10 行和第 106 行（两个 `--surface-app` 定义）改为：
```css
--surface-app: var(--surface-app-atmosphere, var(--neutral-0));
```

使用 fallback 确保未加载 atmosphere 文件时仍正常。

#### Step 6: Signature Glow 动态化 — `src/styles/globals.css`

将第 113 行硬编码值：
```css
--color-signature-glow: oklch(0.760 0.055 74 / 0.60);
```
改为相对色语法：
```css
--color-signature-glow: oklch(from var(--brand-signature-fg) l c h / 0.60);
```

这样 glow 自动跟随 Domain 签名色。项目已使用此语法（`tokens-semantic.css:57`）。

#### Step 7: React 侧设置 `data-domain` — `src/features/shell/components/app-shell.tsx`

新建 hook `src/features/shell/hooks/use-active-domain.ts`：

```typescript
import { useLocation } from "@tanstack/react-router";
import { DOMAINS, type DomainId } from "@/features/navigation/types";

function isDomainActive(domainId: DomainId, pathname: string): boolean {
  const domain = DOMAINS.find((d) => d.id === domainId);
  if (!domain) return false;
  if (domainId === "home") return pathname === "/";
  return pathname.startsWith(domain.path);
}

export function useActiveDomain(): DomainId {
  const { pathname } = useLocation();
  const domain = DOMAINS.find((d) => isDomainActive(d.id, pathname));
  return domain?.id ?? "home";
}
```

在 `app-shell.tsx` 中使用：

```typescript
const activeDomain = useActiveDomain();

useEffect(() => {
  document.documentElement.setAttribute("data-domain", activeDomain);
}, [activeDomain]);
```

---

### Batch 3: 视觉效果（动画 + 氛围）

#### Step 8: 面板呼吸动画 — `src/styles/globals.css`

在现有 keyframes 块后添加：

```css
@keyframes panel-breathe {
  0%, 100% { border-color: var(--border-subtle); }
  50% { border-color: color-mix(in oklch, var(--border-subtle) 90%, var(--color-signature-line) 10%); }
}

[data-slot="panel"] {
  animation: panel-breathe var(--atmosphere-breathe-duration, 45s) ease-in-out infinite;
}
```

使用 `--color-signature-line`（非 `--color-accent`）使呼吸色自动匹配 Domain 签名。45s 周期 + 10% 混合 = 亚感知级。`prefers-reduced-motion` 规则（第 682 行已有）自动禁用。

#### Step 9: 方向性数值光晕 — `src/styles/globals.css`

添加两个新 keyframe：

```css
@keyframes value-flash-up {
  0% {
    text-shadow: 0 3px 6px oklch(from var(--market-up-fg) l c h / 0.08);
    opacity: 0.85;
  }
  100% {
    text-shadow: none;
    opacity: 1;
  }
}

@keyframes value-flash-down {
  0% {
    text-shadow: 0 -3px 6px oklch(from var(--market-down-fg) l c h / 0.08);
    opacity: 0.85;
  }
  100% {
    text-shadow: none;
    opacity: 1;
  }
}
```

非破坏性新增——原 `value-flash` 不变，组件可按需切换到方向性版本。`oklch(from var(...))` 自动适应 intl 市场色彩翻转。

#### Step 10: Atmosphere JS Hook — 新建 `src/features/shell/hooks/use-atmosphere.ts`

```typescript
import { useEffect } from "react";

type MarketPhase = "pre-market" | "active" | "post-market" | "closed";

const PHASE_PROFILES = {
  "pre-market":  { hueShift: 5,  chromaBoost: 0.001,  lightnessShift: 0.002 },
  "active":      { hueShift: 0,  chromaBoost: 0,      lightnessShift: 0 },
  "post-market": { hueShift: -3, chromaBoost: -0.001,  lightnessShift: -0.001 },
  "closed":      { hueShift: -5, chromaBoost: -0.0015, lightnessShift: -0.002 },
} as const;

function getMarketPhase(): MarketPhase {
  const hour = new Date().getHours();
  if (hour >= 9 && hour < 15) return "active";
  if (hour >= 8 && hour < 9) return "pre-market";
  if (hour >= 15 && hour < 16) return "post-market";
  return "closed";
}

export function useAtmosphere(): void {
  useEffect(() => {
    function update() {
      const phase = getMarketPhase();
      const config = PHASE_PROFILES[phase];
      const root = document.documentElement.style;
      root.setProperty("--atmosphere-hue-shift", String(config.hueShift));
      root.setProperty("--atmosphere-chroma-boost", String(config.chromaBoost));
      root.setProperty("--atmosphere-lightness-shift", String(config.lightnessShift));
    }
    update();
    const interval = setInterval(update, 300_000); // 5 分钟检查一次
    return () => clearInterval(interval);
  }, []);
}
```

在 `app-shell.tsx` 中调用 `useAtmosphere()`。

#### Step 11: 背景平滑过渡 — `src/styles/globals.css`

给 `html` 添加背景过渡（约 393 行附近的 `html { height: 100% }` 处）：

```css
html {
  height: 100%;
  transition: background 60s linear;
}
```

---

### 阶段 A 完成后的验证

在进入阶段 B 前，必须确认：
1. **`bun run check`** 通过 ✅ — biome lint 通过，tsc 仅预存错误，vitest 97/1136 全通过
2. 在原型 HTTP 服务器上手动测试 `tokens-atmosphere.css` + `data-domain` 的视觉效果
3. React dev server 验证 `data-domain` 切换正常、atmosphere 渐变生效

---

### 阶段 B: 原型同步（阶段 A 验证通过后执行）— ✅ 已完成

#### Step 12: 更新 30 个 HTML 原型文件 — ✅ 已完成（29/29）

每个 `prototype/page-*.html` 做两处修改：

1. 在 `tokens-semantic.css` 的 `<link>` 后添加：
   ```html
   <link rel="stylesheet" href="../../../../src/styles/design-tokens/tokens-atmosphere.css">
   ```

2. 在 `<html>` 标签上添加 `data-domain` 属性（按页面所属 Domain）：
   - `page-home.html`: `data-domain="home"`
   - `page-trading-overview.html` / `page-orders-ledger.html` / `page-signals-inbox.html` / `page-risk-center.html`: `data-domain="trading"`
   - `page-markets-*.html` / `page-a-shares.html` / `page-cross-market.html` / `page-watchlist.html` / `page-instrument-hub.html` / `page-universe-list.html`: `data-domain="markets"`
   - `page-research.html` / `page-regime-monitor.html` / `page-factor-*.html` / `page-strategy-*.html` / `page-backtest-*.html` / `page-experiment-list.html`: `data-domain="research"`
   - `page-platform.html` / `page-platform-settings.html`: `data-domain="platform"`
   - `page-ai-*.html` / `page-agent-console.html`: `data-domain="ai"`

原型中无 JS hook，atmosphere 默认零值，不影响现有视觉。

---

## 修改文件清单

| 文件 | 操作 | 步骤 |
|------|------|------|
| `src/styles/design-tokens/tokens-atmosphere.css` | **新建** | 1 |
| `src/styles/design-tokens/tokens-semantic.css` | 修改（3 处） | 2, 3, 5 |
| `src/styles/globals.css` | 修改（4 处） | 4, 6, 8, 9, 11 |
| `src/features/shell/hooks/use-active-domain.ts` | **新建** | 7 |
| `src/features/shell/hooks/use-atmosphere.ts` | **新建** | 10 |
| `src/features/shell/components/app-shell.tsx` | 修改 | 7, 10 |
| 30 个 `prototype/page-*.html` | 修改 | 12 |

---

## Metric Hero 模式（文档级，Pillar 3b）

非代码变更。模式定义：

- **适用场景**：面板中最核心的 1-3 个数值（P&L 总额、持仓敞口、风险评分）
- **Token 组合**：`text-2xl`（24px）+ `font-data`（JetBrains Mono）+ `font-semibold` + `text-(--color-foreground)`
- **效果**：数值成为面板的"视觉标题"，标签退居"注释"

已有 token 支撑，无需新增。在各页面组件中按需应用。

---

## 验证计划

### 阶段 A 验证

1. **`bun run check`** — lint + type + test 全部通过
2. **Token 值验证** — 确认 `oklch(calc(...))` 在浏览器中正确解析
3. **React 页面 QA** — 启动 dev server，逐页检查：
   - `data-domain` 属性正确设置
   - 签名色随导航切换
   - atmosphere 默认零值 = 与当前完全一致
4. **亮色模式测试** — 所有 Domain 签名色在 light theme 下显示正常
5. **`prefers-reduced-motion` 测试** — 动画正确禁用

### 阶段 B 验证

1. **原型视觉 QA** — 逐一检查 30 个原型页面，确认：
   - Domain 签名色正确显示（header 底线、rail 光条、panel 呼吸色）
   - 文本对比度变化无副作用（无文字消失或过亮）
   - atmosphere 默认零值 = 与当前完全一致
2. **跨浏览器测试** — `oklch(calc(...))` 和 `oklch(from ...)` 支持
3. **数值光晕方向性** — 如已有组件使用 `value-flash`，切换到 `value-flash-up/down`

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| `oklch(calc(...))` 浏览器兼容性 | Step 1 前验证；回退方案为 4 个离散 surface 值 |
| 文本对比度变化影响 30 个原型 | Batch 1 独立提交，一条 revert 即可 |
| Domain 签名色在亮色下冲突 | 为每个 Domain 独立设计亮色值 |
| 面板呼吸在高密度布局中显得多余 | 45s 周期 + 10% 混合 = 亚感知；`prefers-reduced-motion` 自动禁用 |
| `data-domain` 与未来属性冲突 | 同 pattern 的 `data-theme`/`data-density` 已验证可行 |
