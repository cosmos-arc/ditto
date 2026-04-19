# 视觉还原验证规范

> **铁律**：Token 正确 ≠ 视觉正确。布局比例错误比 token 错误更严重，因为后者可被测试捕获，前者不能。

---

## 核心原则

### 1. 四层验证模型

| 层级 | 验证内容 | 工具 | 通过标准 |
|------|---------|------|---------|
| **L0 完整性** | Prototype 所有模块都有 React 实现 | 结构对比 | 0 遗漏 |
| **L1 Token** | token 引用合规 | 合规测试（grep） | 0 违规 |
| **L2 布局** | 元素尺寸与 prototype 一致 | Playwright `page.evaluate()` 提取 bounding rect | 偏差 < 3% |
| **L2.5 微观样式** | 字号/字重/颜色/间距/圆角一致 | Playwright `getComputedStyle()` 对比 | 偏差在阈值内 |
| **L3 像素** | 整体视觉对齐 | Playwright `toHaveScreenshot()` 像素级对比 | 匹配度 > 98% |

**必须全部通过才能声称"原型对齐"。**

### 2. 浏览器引擎统一

> **度量提取和验证必须在同一浏览器引擎中执行。** 混合 Chrome DevTools + Playwright 不同 headless 模式会产生虚假偏差。

| 场景 | 配置 | 说明 |
|------|------|------|
| 度量提取（Phase 10） | `chromium.launch({ channel: 'chromium' })` | 新 headless = 真实 Chrome 渲染引擎 |
| 布局验证（Phase 14 L2） | 同上 | 同一 viewport、同一 channel |
| 像素验证（Phase 14 L3） | 同上 | 确保 L2 和 L3 像素一致性 |

**必须使用 `channel: 'chromium'`**（新 headless），而非默认 old headless。
原因：old headless 是独立的渲染管线，字体渲染、抗锯齿与真实 Chrome 不同，会导致像素级虚假差异。

**已废弃**：Chrome DevTools 手动 `evaluate_script`。所有度量提取和验证统一到 Playwright。

### 3. 禁止的验证方式

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| AI vision 泛化描述对比（"都是深色仪表盘"） | 逐元素 bounding rect 数值对比 |
| 只看 token 是否正确就声称视觉一致 | 同时验证布局比例 + 微观样式 |
| "bun run check 通过" = 原型对齐 | 工程通过 ≠ 视觉对齐 |
| 截图 "看起来差不多" | Playwright `toHaveScreenshot()` 像素级差异检测 |
| 只对比颜色值（oklch 一致） | 同时对比尺寸、位置、间距 |
| 只检查 bounding rect（L2） | 同时检查 computed styles（L2.5） |
| Chrome DevTools 手动提取度量 | Playwright `page.evaluate()` 自动化 |
| 默认 old headless 做像素对比 | `channel: 'chromium'` 新 headless |
| "组件存在" = 视觉正确 | 组件存在 ≠ 数据填充正确 ≠ 样式正确 |
| 跳过 L0 完整性检查 | 先确认 prototype 每个模块都有 React 实现 |

---

## 强制流程

### 实现前：度量 Prototype

**在写任何 React 代码之前，必须先从 prototype HTML 提取布局度量。**

使用 Playwright 自动提取（详见 `/ditto-app-dev --implement` Phase 10）：

```js
const browser = await chromium.launch({ channel: 'chromium' });
const page = await browser.newPage({ viewport: { width: 1536, height: 900 } });

// 启动 prototype HTTP 服务 + 注入标准化 CSS
await page.goto('http://localhost:8888/page-xxx.html');
await page.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });
await page.waitForLoadState('networkidle');

// 提取关键区域度量
const metrics = await page.evaluate(() => {
  const items = [];
  document.querySelectorAll('.panel, .decision-banner, .panel-grow, .context-rail, .shell-main, .main-primary, .secondary-grid').forEach(el => {
    const rect = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    items.push({
      cls: el.className.substring(0, 60),
      x: Math.round(rect.x), y: Math.round(rect.y),
      w: Math.round(rect.width), h: Math.round(rect.height),
      display: cs.display,
      gridCols: cs.gridTemplateColumns?.substring(0, 80),
      gridRows: cs.gridTemplateRows?.substring(0, 80),
      flex: cs.flex,
      padding: cs.padding,
      gap: cs.gap,
    });
  });
  return items;
});
```

**必须提取的度量数据**：

```
每个命名区域必须记录：
- 实际像素高度（h）
- 布局策略（content-driven / flex-N / fixed-Npx / percentage）
- grid-template 值
- padding / gap 值
- 父级容器的 grid/flex 分配策略
```

**必须记录到页面合同的度量字段**。

**标准化 CSS**（复用 `.claude/skills/ditto-app-dev/scripts/visual-audit.config.mjs` 中的 `PROTOTYPE_NORMALIZE_CSS`）：
- 隐藏 `.proto-nav`（原型的导航 UI，React 端不存在）
- 强制 `#default-view` 为 100vh
- 固定 status-bar 高度

### 实现中：禁止无依据的百分比

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| `max-h-[66%]` 无 prototype 依据 | 从 prototype 提取实际像素高度，反推策略 |
| `h-[50%]` 猜测比例 | prototype 用 content-driven → React 也用 content-driven |
| `flex-[2_1_0]` 随意分配 | 从 prototype 的 grid-template 值精确复制 |

**判断规则**：

1. 如果 prototype 用 `1fr` → React 用 `flex-1`
2. 如果 prototype 用固定 `px` → React 用对应 token 或固定值
3. 如果 prototype 用 `auto`（内容驱动）→ React 不设高度约束
4. **如果 prototype 没有百分比布局 → React 也不要用百分比**

### 实现后：四层验证

#### L0：组件完整性验证（实现前 + 实现后）

**在写任何代码之前，先确认 prototype 的每个模块都有 React 实现。**

```
Prototype 模块清单 → React 组件清单 → diff = 缺失列表
```

**检查项**：
1. Prototype 每个命名 section（`.panel`、`.decision-banner`、`.context-section`、`.workspace-placeholder` 等）在 React 中有对应组件
2. 每个 React 组件都有数据源（hook/mock）且 mock 数据**非空数组**
3. 组件使用正确的数据源（不要 `AgentFindingsSection` 调用 `useRecentSignals()` 返回空数组这种错误）
4. 组件容器模式一致（都用 `<Panel>` 或都用 raw div，不要混用）

**已踩过的坑**：
- Workspace Placeholder 在 prototype 中存在但 React 未实现 → 页面布局缺一块
- `AgentFindingsSection` 调用 `useRecentSignals()` 但 mock 返回 `[]` → 区域渲染为空
- `PulseSection` 的风险等级和 Regime 标签硬编码 → 数据与 API 脱节

#### L1：Token 验证（自动）

```bash
bun run test --run src/features/shell/design-system-compliance.test.ts
```

#### L2：布局验证（Playwright 自动化）

**使用 Playwright 对 prototype 和 React 两侧分别执行 `page.evaluate()` 提取 bounding rect，然后程序化对比。**

现有自动化工具：`.claude/skills/ditto-app-dev/scripts/visual-audit.mjs`

```bash
# 运行全页面 L2 验证
bun .claude/skills/ditto-app-dev/scripts/visual-audit.mjs --all \
  --react-base http://localhost:5173 \
  --prototype-base http://localhost:8888

# 运行单页面 L2 验证
bun .claude/skills/ditto-app-dev/scripts/visual-audit.mjs --route / \
  --react-base http://localhost:5173 \
  --prototype-base http://localhost:8888
```

**通过标准**：
- 宽度偏差 < 3%
- 高度偏差 < 3%（content-driven 区域放宽至 < 5%）
- x/y 偏移 < 4px

**输出**：`docs/review/visual-audit/<page>/metrics.json` + `report.md`

#### L2.5：微观样式验证（Playwright 自动化）

**L2 只检查 bounding rect（位置/尺寸），不检查内部样式。L2.5 补充检查 computed styles。**

```js
// 从 prototype 和 React 提取相同选择器的 computed styles
const styles = await page.evaluate(() => {
  const selectors = [
    '.shell-rail', '.shell-header', '.shell-pulse',
    '.panel-header .panel-title', '.queue-item',
    '.pulse-item', '.context-section-title',
  ];
  return selectors.map(sel => {
    const el = document.querySelector(sel);
    if (!el) return { selector: sel, found: false };
    const cs = getComputedStyle(el);
    return {
      selector: sel,
      found: true,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      color: cs.color,
      backgroundColor: cs.backgroundColor,
      padding: cs.padding,
      gap: cs.gap,
      borderRadius: cs.borderRadius,
      letterSpacing: cs.letterSpacing,
      lineHeight: cs.lineHeight,
    };
  });
});
```

**必须对比的属性**：

| 属性 | 阈值 | 说明 |
|------|------|------|
| `fontSize` | ±1px | 字号偏差 |
| `fontWeight` | 完全匹配 | 字重不能有差异 |
| `color` | oklch 完全匹配 | 文本色必须一致 |
| `backgroundColor` | oklch 完全匹配 | 背景色必须一致 |
| `padding` | ±2px | 内边距偏差 |
| `gap` | ±2px | 间距偏差 |
| `borderRadius` | ±1px | 圆角偏差 |
| `letterSpacing` | ±0.02em | 字距偏差 |

**通过标准**：所有检查属性在阈值内，0 个超标。

#### L3：像素验证（Playwright 自动化）

```js
// 两侧截图（mask 动态内容）
await prototypePage.screenshot({ path: 'prototype.png' });
await reactPage.screenshot({
  path: 'react.png',
  mask: [page.locator('.timestamp'), page.locator('.live-data')],
});

// Playwright 内置像素对比
expect(await reactPage.screenshot()).toMatchSnapshot({
  maxDiffPixelRatio: 0.02,  // 2% 容差
  threshold: 0.2,
});
```

**通过标准**：像素匹配 > 98%（`maxDiffPixelRatio < 0.02`）。

---

## 常见陷阱

### 陷阱 1："组件存在就够了"

组件存在 ≠ 布局正确。一个 `PriorityQueueSection` 渲染了 5 个 queue item，但如果容器给了 367px 而非 prototype 的 120px，信息密度就完全错了。

**检查方式**：对比每个 section 的实际渲染高度。

### 陷阱 2："grid-template 值一样就够了"

`grid-cols-[5fr_4fr_3fr]` 正确，但如果外层容器的高度分配错了（如 `max-h-[66%]`），内部 grid 再正确也没用。

**检查方式**：从最外层容器开始，逐层验证尺寸。

### 陷阱 3："颜色对了就对了"

所有 oklch 值完全一致，但 banner 高 180px vs prototype 149px，queue 高 367px vs prototype 120px——颜色正确但布局完全错位。

**检查方式**：先验证布局尺寸，再验证颜色。

### 陷阱 4："DevTools 和 Playwright 结果一样"

对于 `getBoundingClientRect()` 和 `getComputedStyle()`，L2 布局度量确实一致。
但对于 L3 像素截图，old headless（Playwright 默认）与真实 Chrome 的字体渲染、抗锯齿不同，会产生 2-5px 虚假差异。

**解决方式**：统一使用 `channel: 'chromium'`（新 headless）。

### 陷阱 5："Token 值统一了就万事大吉"

Token 同步（SSOT）解决的是**值漂移**问题——同一 token 在 Prototype 和 React 不再有两套不同的值。
但它**不能解决**以下问题：

| 问题 | Token 能解决？ | 正确解法 |
|------|:---:|---------|
| 两端颜色值不同 | ✅ | 共享 token 文件 |
| 字号档位塌缩（text-xl = text-lg） | ❌ | 在 prototype 中新增字号档位 |
| React 组件缺失 | ❌ | 实现缺失的组件 |
| Mock 数据为空导致区域空白 | ❌ | 补充 mock 数据 |
| 硬编码假数据 | ❌ | 接入真实 API 或丰富 mock |
| 容器高度策略错误 | ❌ | 从 prototype 提取度量后精确实现 |
| `@theme inline` 变量在 `:root` 中 undefined | ❌ | 用具体值而非 `var(--spacing-*)` |

**解决方式**：Token 统一后，仍需 L0 完整性 + L2.5 微观样式 + 人工视觉检查。

### 陷阱 6："@theme inline 变量可以随处引用"

`@theme inline` 中的变量（如 `--spacing-4`、`--text-sm`）只在 Tailwind utility 内部可用。
在 `:root {}`、`[data-theme]`、`globals.css` 的组件样式中用 `var(--spacing-4)` 会得到 undefined。

**解决方式**：
- 需要在 CSS 变量上下文中引用的值 → 在 `:root` 中定义（如 `tokens-base.css`）
- 只在 Tailwind utility 中使用的值 → `@theme inline`

### 陷阱 7："Mock 数据空数组不影响视觉验证"

Mock hook 返回空数组 `[]` 时，React 组件的列表区域会渲染为空——但 bounding rect 仍然存在（容器高度可能是 0 或最小高度），L2 验证可能通过，但**视觉上明显缺失内容**。

**解决方式**：L0 完整性检查中，必须确认每个列表组件的 mock 数据**非空**且与 prototype 数量一致。

### 陷阱 8："pixelmatch 默认输出可以当 diff mask 用"

pixelmatch v7+ 默认对所有像素（包括匹配像素）写入 alpha=255 的灰度值。
`drawGrayPixel()` 把匹配像素画成灰度，把差异像素画成红/黄。
如果不传 `diffMask: true`，diff 输出是一张全不透明图片，无法用于提取纯差异区域。

**解决方式**：
```js
// ❌ 错误：所有像素都有 alpha=255，无法区分匹配/不匹配
pixelmatch(a, b, diff, w, h, { threshold: 0.1 });

// ✅ 正确：只有不匹配像素有 alpha>0
pixelmatch(a, b, diff, w, h, { threshold: 0.1, diffMask: true });
```

### 陷阱 9："data-slot 选择器直接映射 prototype class 即可"

React 用 `data-slot` 属性标记布局区域，但视觉上有意义的元素不一定是直接 slot 容器。
例如：`[data-slot='pulse']` 是一个透明的 grid-area wrapper，而 `[data-slot='pulse-strip']` 才是实际带样式、有边框的内部 div。
映射错了，L2 度量对比的就是一个透明元素——边框/颜色/zIndex 全是 inherited/fallback 值。

**解决方式**：在 `.claude/skills/ditto-app-dev/scripts/visual-audit.config.mjs` 中配置时，先用浏览器 DevTools 确认哪个 `data-slot` 元素实际承载了样式（`getComputedStyle()` 有非默认 border/background 等）。

**已踩过的坑**：
- `strip: "[data-slot='pulse']"` → 透明 wrapper，应改为 `"[data-slot='pulse-strip']"`
- `sidebar: "[data-slot='sidebar']"` → 透明 wrapper，应改为 `"[data-slot='sidebar-rail']"`

### 陷阱 10："L3 像素差异可以降到 0%"

L3 像素对比的理论天花板不是 0%，而是由**浏览器字体抗锯齿（AA）**决定的。
Prototype（纯 HTML）和 React（SPA）即使布局完全一致，文字边缘的亚像素渲染仍有差异（通常 1-4%）。

**判断方法**：
1. 生成 diff 可视化（红点 + 暗化背景）
2. 用 AI 图像分析或目视确认：差异是否集中在文字边缘
3. 检查垂直 band 分布：文字密集区域（如 sidebar 列表）差异更高

**L3 分数解读**：
| 原始比例 | threshold 0.2 | threshold 0.3 | 评估 |
|---------|:---:|:---:|------|
| < 2% | — | — | 优秀，AA 也可忽略 |
| 2-4% | pass | — | 良好，差异为 AA 伪影 |
| 4-6% | fail | pass | 可接受，需确认非布局问题 |
| > 6% | fail | fail | 需要排查实现问题 |

**结论**：L3 不是唯一标准。L2 布局偏差 < 3px + L3 差异集中在文字 AA = 实现层已达标。

---

## Checklist（实现每个 prototype-backed 页面前必过）

- [ ] **L0** Prototype 每个命名 section 都有 React 组件对应（0 遗漏）
- [ ] **L0** 每个 React 组件的 mock 数据非空，数量与 prototype 一致
- [ ] **L0** 组件使用正确的数据源 hook（无语义错配）
- [ ] **L0** 容器模式一致（都用 Panel 或都用 raw div，不混用）
- [ ] 用 Playwright（`channel: 'chromium'`）提取了完整布局度量
- [ ] 度量数据记录在页面合同或设计文档中
- [ ] React 实现的每个 section 布局策略（content-driven / flex / fixed）与 prototype 一致
- [ ] 没有使用无 prototype 依据的百分比高度/宽度
- [ ] **L1** Token 验证通过（0 违规）
- [ ] **L2** 布局验证通过（偏差 < 3%）
- [ ] **L2.5** 微观样式验证通过（fontSize/fontWeight/color/padding/gap/borderRadius 在阈值内）
- [ ] **L3** 像素验证通过（匹配度 > 98%）
- [ ] L2 和 L3 使用同一 Playwright 浏览器配置
- [ ] 无硬编码假数据（风险等级、Regime 标签、子文本等应来自 API 或丰富 mock）
