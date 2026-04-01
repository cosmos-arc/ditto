# Ditto 排版系统规范 v2

> **日期**：2026-03-31
> **状态**：Approved
> **替换**：[2026-03-28-key-design-decisions.md §2-3](../designs/decisions/2026-03-28-key-design-decisions.md)（字体相关）
> **关联**：[15_ditto_token_stabilization_spec.md](../designs/specs/15_ditto_token_stabilization_spec.md)

---

## 概述

将 Ditto 的字体系统从 3 套 token 升级为 4 套 token（body / heading / data / code），每个字族按其官方定位分配独立职责，并新增 line-height token、OpenType 排版规则绑定。

### 核心变更

| 维度 | 旧方案 | 新方案 |
|------|--------|--------|
| Token 数量 | 3（ui / numeric / code） | 4（body / heading / data / code） |
| 正文字体 | Inter + Noto Sans SC | Inter + Noto Sans SC Variable |
| 标题字体 | 无独立 token | Geist Sans |
| 数据字体 | JetBrains Mono（等宽） | Inter（proportional + OpenType） |
| 代码字体 | JetBrains Mono | Geist Mono（JetBrains Mono 降级为 fallback） |
| 中文底座 | Noto Sans SC | Source Han / Noto 同源路线（v1 实际加载 Noto Sans SC Variable） |
| line-height | 硬编码 1.5 | 3 级 token（1.25 / 1.45 / 1.60） |
| OpenType | 无 | data: tabular-nums + slashed-zero; code: ligatures off |

---

## 1. Token 定义

```css
:root {
  /* ── Font Families (4-role system) ── */
  --font-family-body:
    "Inter",
    "Noto Sans SC Variable",
    "Source Han Sans SC",
    "PingFang SC",
    system-ui,
    -apple-system,
    sans-serif;

  --font-family-heading:
    "Geist Sans",
    "Inter",
    "Noto Sans SC Variable",
    "Source Han Sans SC",
    "PingFang SC",
    system-ui,
    -apple-system,
    sans-serif;

  --font-family-data:
    "Inter",
    "Noto Sans SC Variable",
    "Source Han Sans SC",
    "PingFang SC",
    system-ui,
    sans-serif;

  --font-family-code:
    "Geist Mono",
    "JetBrains Mono",
    ui-monospace,
    SFMono-Regular,
    Consolas,
    monospace;

  /* ── Line Heights ── */
  --line-height-compact:  1.25;
  --line-height-normal:   1.45;
  --line-height-relaxed:  1.60;

  /* ── Weights (unchanged) ── */
  --font-weight-regular:  400;
  --font-weight-medium:   500;
  --font-weight-semibold: 600;
}
```

### 关于 Noto Sans SC Variable 排在 Source Han Sans SC 前面

v1 实际加载的是 Fontsource 提供的 Noto Sans SC Variable，CSS font-family 必须先写浏览器能命中的真实加载名。规范文档层面仍称中文底座为"Source Han / Noto 同源路线"（Adobe 官方确认 Source Han Sans 和 Noto Sans CJK 机械层面 identical）。

v2 如切换到 self-host 的 Source Han Sans SC 子集，调换顺序即可，token 名不变。

---

## 2. Tailwind @theme 桥接

替换 `src/styles/globals.css` 中 `@theme inline` 的 Fonts 部分：

```css
@theme inline {
  /* ── Fonts ── */
  --font-body:    var(--font-family-body);
  --font-heading: var(--font-family-heading);
  --font-data:    var(--font-family-data);
  --font-code:    var(--font-family-code);
}
```

Tailwind 工具类：`font-body` / `font-heading` / `font-data` / `font-code`。

旧工具类 `font-ui` / `font-numeric` 失效。

---

## 3. OpenType 规则

与 token 绑定的排版行为规则。`tabular-nums` 与 `slashed-zero` 只在明确的数据展示组件上启用；正文与说明文字保持自然比例排版。代码相关组件默认关闭 ligatures，保证逐字符核对的准确性。

```css
/* ── Data: 数字对齐 + 零区分 ── */
.numeric,
.data-grid,
.kpi-value,
.price,
.pnl,
.time,
.symbol-code,
.ratio,
.percent {
  font-family: var(--font-family-data);
  font-variant-numeric: tabular-nums slashed-zero;
}

/* ── Code: 默认关闭连字 ── */
.code,
.editor,
.log,
.dsl,
.sql,
.terminal,
.trace {
  font-family: var(--font-family-code);
  font-variant-ligatures: none;
}
```

### 设计决策

**为什么 `tabular-nums` 不全局开启？** 因为它适用于结构化数字展示，不适合正文中的自然数字排版（年份、百分比、版本号、日期、编号没必要全部等宽化）；`slashed-zero` 也只对需要精确辨识 0/O 的数值与代码场景有意义。

**Code ligatures 例外说明：** 上述规则适用于逐字符核对场景。品牌演示页或 marketing 式 code snippet 不在此列，可按需局部开启。

---

## 4. 组件级字体分配

| Token | 语义 | 适用组件/区域 |
|-------|------|---------------|
| `heading` | 气质层 | 页面标题、模块标题、一级导航、Command Palette 标题 |
| `body` | 底座层 | 正文、表单、筛选器、tooltip/popover、二级导航、表格中文列名、KPI 标签（关键模块可例外用 heading）、类目轴/混合文本轴标签、`.symbol-name` |
| `data` | 精度层 | 价格、收益率、仓位、PnL、watchlist 数字列、日期时间、回测指标、纯数值轴标签、`.symbol-code` + `tabular-nums slashed-zero` |
| `code` | 终端层 | 代码编辑器、DSL 表达式、日志、终端、trace、SQL + `font-variant-ligatures: none` |

### KPI 标签归属说明

KPI 标签（"总收益率""年化收益""当前回撤"）本质上不是标题，而是数据注释文本。它们通常字号小、密度高、重复出现。默认走 `body`，仅首页主卡或极少数关键模块可例外用 `heading`。

### 坐标轴标签拆分

- 纯数值轴（Y 轴：`12.5%`、`8,000`、`1.23`）→ `data`
- 类目轴/混合文本轴（X 轴：`银行`、`2026-Q1`、`近5日`）→ `body`

### 示例：KPI 卡片

```tsx
<div className="kpi-card">
  {/* 标签用 body（非 heading） */}
  <span className="font-body font-medium text-[12px] text-text-secondary">
    总收益率
  </span>
  {/* 数值用 data + OpenType */}
  <span className="font-data text-[24px] tabular-nums slashed-zero">
    +12.34%
  </span>
</div>
```

### 示例：Ticker / 标的

```tsx
<div className="ticker-cell">
  {/* 代码走 data */}
  <span className="font-data text-[13px]">AAPL</span>
  {/* 中文名走 body */}
  <span className="font-body text-[11px] text-text-tertiary">
    苹果公司
  </span>
</div>
```

---

## 5. 字重使用边界

| 字重 | 用途 | 不用于 |
|------|------|--------|
| 400 | 正文、表格正文、表单输入、tooltip | 标题 |
| 500 | 二级标题、表头、导航项、按钮文字、KPI 标签 | 大面积正文（会显重） |
| 600 | 一级标题、关键模块标题、极少量强调 | 导航、按钮、表头、KPI 标签 |

**Geist Sans 在暗色 + 600 下视觉冲击力很强，克制使用才有"买方终端"气质，到处 600 就变"Vercel Dashboard"。**

---

## 6. 字体加载

### Geist Sans + Geist Mono

通过 `@fontsource-variable` npm 包，显式 import `/wght.css`：

```ts
// main.tsx
import "@fontsource-variable/geist-sans/wght.css";   // swap
import "@fontsource-variable/geist-mono/wght.css";    // swap
```

显式 `/wght.css` import 明确启用 variable weight 轴，可读、可维护。

预估体积（variable WOFF2）：
- Geist Sans: ~60KB
- Geist Mono: ~45KB

### Noto Sans SC（font-display: optional）

**不走 Fontsource 默认 CSS import。** Fontsource 默认 `font-display: swap`，对中文正文底座不合适。

在 `src/styles/fonts.css` 中自定义 `@font-face`，引用 Fontsource 包内的字体文件，手动设置 `font-display: optional`：

```css
/* ── Noto Sans SC: font-display: optional（中文正文底座不跳变） ── */
@font-face {
  font-family: "Noto Sans SC Variable";
  src: url("@fontsource-variable/noto-sans-sc/files/noto-sans-sc-chinese-simplified.woff2")
       format("woff2");
  font-weight: 100 900;
  font-style: normal;
  font-display: optional;
  unicode-range: U+4E00-9FFF, U+3400-4DBF, U+2E80-2EFF, U+3000-303F,
                 U+FF00-FFEF, U+2F00-2FDF, U+3100-312F;
}
```

`optional` 的含义：如果字体在极短时间窗口内就绪就用，否则放弃，永远用 fallback。对 Ditto 这种高密暗色终端，正文不跳变比"用上最正确的字体"更重要。

> 实际 `src` 路径需根据 Fontsource 包内文件结构确认，上述为示意写法。

### Inter

已在项目中使用，保持现有加载机制不变。

### font-display 策略汇总

| 字体 | font-display | 理由 |
|------|-------------|------|
| Inter | 现状不变 | 已就绪 |
| Geist Sans | `swap` | 首屏标题可见，尽快切换 |
| Geist Mono | `swap` | 非首屏主阅读字体，不敏感 |
| Noto Sans SC | **`optional`** | 中文正文底座，稳定性优于几百毫秒的"正确字体" |

### unicode-range 定位

保留，但明确其作用是**按字符出现与否的下载门槛**，不是单文件体积优化手段：

- 纯拉丁路由（如果未来有英文版界面）：CJK 字体不会下载
- 中文路由：CJK 字体会整体下载，`unicode-range` 不拆分文件

如未来需要真正分段加载 CJK，需将字体拆成多个文件配合多段 `unicode-range`，但 v1 不做此复杂度。

### 加载优先级

| 优先级 | 字体 | 策略 |
|--------|------|------|
| Critical | Inter | 已就绪 |
| High | Geist Sans | `@fontsource-variable` + `swap` |
| High (non-blocking) | Noto Sans SC | 本地 `@font-face` + `optional` |
| Medium | Geist Mono | `@fontsource-variable` + `swap` |
| Fallback only | PingFang SC, system-ui, JetBrains Mono | 系统自带 / 已加载 |

---

## 7. body 基础样式

```css
body {
  height: 100%;
  overflow: hidden;
  background: var(--surface-app);
  color: var(--text-primary);
  font-family: var(--font-family-body);
  font-size: var(--font-size-13);
  line-height: var(--line-height-normal);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

变更：`line-height: 1.5` → `var(--line-height-normal)`。

---

## 8. Cloudflare Pages 缓存策略

`public/_headers`：

```
/assets/*.woff2
  Cache-Control: public, max-age=31536000, immutable
```

Vite 构建的字体产物自带 hash 文件名，天然适合长缓存。一次命中后不再请求。

---

## 9. 新增 npm 依赖

```bash
bun add @fontsource-variable/geist-sans
bun add @fontsource-variable/geist-mono
bun add @fontsource-variable/noto-sans-sc
```

> Noto Sans SC 包仅提供字体文件（woff2），不 import 其默认 CSS。

---

## 10. 废弃清单

| 旧 Token | 替换为 |
|----------|--------|
| `--font-family-ui` | `--font-family-body`（正文）+ `--font-family-heading`（标题） |
| `--font-family-numeric` | `--font-family-data` |
| `--font-family-code` | `--font-family-code`（值从 JetBrains Mono → Geist Mono） |
| `--font-ui`（@theme） | `--font-body` |
| `--font-numeric`（@theme） | `--font-data` |
| `line-height: 1.5`（硬编码） | `var(--line-height-normal)` |

---

## 11. 迁移影响

### 产品代码

| 文件 | 变更 |
|------|------|
| `src/styles/globals.css:83-86` | `@theme inline` 桥接更新 |
| `src/styles/globals.css:143-162` | 删除旧 3 token，新增 4 token + 3 line-height token |
| `src/styles/globals.css:359-361` | body 改用新 token |
| `src/styles/fonts.css`（新建） | Noto Sans SC 自定义 `@font-face` |
| `src/main.tsx` | 添加字体 import |
| `public/_headers`（新建或追加） | woff2 长缓存 |

**TSX 零改动。** 现有组件都走 Tailwind 默认 sans，迁移后 `font-body` 成为新默认。

### 规范文档

| 文件 | 变更 |
|------|------|
| `docs/designs/decisions/2026-03-28-key-design-decisions.md §2-3` | 替换字体决策 |
| `docs/designs/specs/15_ditto_token_stabilization_spec.md:198-208` | 字体家族表 3→4 行，字重用法收紧 |
| `.claude/design-review/roles.md:9,18` | 审查维度补充 4-role system + OpenType |
| `.claude/design-review/templates.md:189` | Token 一致性检查表补充 |

### 原型文件（延后同步）

`docs/designs/specs/prototypes/` 下 36 个文件、180+ 处引用旧 token。原型是独立产物，不影响产品代码，可在规范落定后批量更新。

---

## 附录：字族定位与选型理由

| 字族 | 官方定位 | Ditto 职责 |
|------|---------|-----------|
| **Inter** | 为 computer screens 设计，提供 tabular numbers 与 slashed zero | 正文底座 + 数据精度层 |
| **Geist Sans** | 面向开发者与设计师，带瑞士设计取向 | 气质层（标题/导航） |
| **Geist Mono** | code editors, diagrams, terminals | 代码/终端层 |
| **Source Han Sans SC** | Pan-CJK 开源字族，SIL OFL 1.1 | 中文设计基座（v1 加载同源 Noto Sans SC） |
| **PingFang SC** | Apple 系统中文 | 平台 fallback |
| **JetBrains Mono** | 代码阅读等宽字体 | code fallback |

> Geist 家族更偏开发者气质与代码界面，Inter 更偏屏幕数据可读性，Source Han 更适合作为稳定的 CJK 底座。数字不再用 mono，标题不再等于正文，中文以一致性优先，Geist 只负责气质层。
