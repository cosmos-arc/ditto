# v3 交互框架实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 全量实施 v3 交互框架设计决策（D1-D4），在 v2 基础上增强折叠态浓缩信息、调整 Drawer 宽度、完成 21 个页面的 L1/L2/L3 信息分配标注与布局调整。

**Architecture:** 基于已有的 Shell 布局 + Zustand 状态管理 + shadcn Sheet Drawer 基础设施，新增 MiniSparkline 共享组件，增强各页面 CollapsedSidebar 浓缩信息，调整 Drawer 宽度 token，逐页标注 L1/L2/L3 信息层级并调整 L3 内容到 Drawer/Tab。

**Tech Stack:** React + TypeScript + Tailwind CSS v4 + Zustand + Radix UI + Vitest

---

## 完成状态总览

| Phase | 内容 | 状态 | 说明 |
|-------|------|------|------|
| **P1** | Token 更新（56px collapsed width） | ✅ 已完成 | `tokens-shell.css` 已定义，globals.css 已映射 |
| **P2** | layout-base.css 面板折叠动画 + 浓缩态样式 | 🔶 基础完成，需增强 | CSS transition ✅，浓缩信息需丰富化 |
| **P3** | Home 页面浓缩态 | 🔶 基础完成，需增强 | `HomeCollapsedSidebar` 已有，缺 mini sparkline |
| **P4** | Intelligence/Hub 页面浓缩态 | 🔶 基础完成，需增强 | `IntelligenceCollapsedSidebar` 已有，缺 mini sparkline |
| **P5** | Orders Ledger trace → Drawer | ✅ 已完成 | `orders-page.tsx` 已使用 Drawer，测试已覆盖 |
| **P6** | Risk Center breach → Drawer | ✅ 已完成 | `risk-page.tsx` 已使用 Drawer，测试已覆盖 |
| **P7** | 各页面 L1/L2/L3 信息分配 | ❌ 待实施 | 标注 + 布局调整 |

---

## Task 1: Drawer 宽度 Token 调整

**复杂度:** S | **依赖:** 无

**Files:**
- Modify: `src/styles/design-tokens/tokens-shell.css:14`
- Modify: `src/components/indicator/overlay/drawer.tsx`
- Modify: `src/components/indicator/overlay/drawer.test.tsx`

**背景:** 设计文档 D3 要求 Drawer 宽度 400-480px（比原面板更宽，利用释放的空间）。当前 `--shell-detail-width: 340px`，Drawer 使用 `w-(--width-detail)` 引用该值。需要新增 Drawer 专用 token，不影响其他使用 `--shell-detail-width` 的组件。

**Step 1: 写失败测试**

在 `drawer.test.tsx` 中新增测试，验证 Drawer 使用新的宽度 token：

```typescript
it("uses v3 drawer width token (440px)", async () => {
	render(
		<Drawer open={true} onClose={() => {}} title="Test">
			Content
		</Drawer>,
	);
	await waitFor(() => {
		const content = document.querySelector("[data-slot='sheet-content']") as HTMLElement;
		expect(content).toBeInTheDocument();
		expect(content.className).toContain("w-(--width-drawer)");
		expect(content.className).toContain("max-w-(--width-drawer)");
	});
});
```

**Step 2: 运行测试确认失败**

Run: `bun run test --run src/components/indicator/overlay/drawer.test.tsx`
Expected: FAIL — className 中仍包含 `w-(--width-detail)` 而非 `w-(--width-drawer)`

**Step 3: 新增 Drawer 宽度 token**

在 `tokens-shell.css` 的 `:root` 中新增：

```css
--shell-drawer-width: 440px;
```

在 `globals.css` 的 `@theme inline` 映射区新增：

```css
--width-drawer: var(--shell-drawer-width);
```

**Step 4: 更新 Drawer 组件**

修改 `drawer.tsx` 中 `SheetContent` 的 className：

```diff
- className={cn("w-(--width-detail) max-w-(--width-detail) p-0", className)}
+ className={cn("w-(--width-drawer) max-w-(--width-drawer) p-0", className)}
```

**Step 5: 运行测试确认通过**

Run: `bun run test --run src/components/indicator/overlay/drawer.test.tsx`
Expected: PASS

**Step 6: Commit**

```bash
git add src/styles/design-tokens/tokens-shell.css src/styles/globals.css src/components/indicator/overlay/drawer.tsx src/components/indicator/overlay/drawer.test.tsx
git commit -m "feat(shell): v3 drawer width token — 440px per D3 spec"
```

---

## Task 2: MiniSparkline 共享组件

**复杂度:** S | **依赖:** 无

**Files:**
- Create: `src/components/data-viz/mini-sparkline.tsx`
- Create: `src/components/data-viz/mini-sparkline.test.tsx`
- Create: `src/components/data-viz/index.ts`

**背景:** 设计文档 D2 要求折叠态显示 mini sparkline（24×12px）。这是一个纯展示型 SVG 组件，接收数据点数组，渲染为折线。

**Step 1: 写失败测试**

创建 `src/components/data-viz/mini-sparkline.test.tsx`：

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MiniSparkline } from "./mini-sparkline";

describe("MiniSparkline", () => {
	it("renders SVG element with accessible role", () => {
		render(<MiniSparkline data={[1, 3, 2, 5, 4]} />);
		const svg = document.querySelector("svg");
		expect(svg).toBeInTheDocument();
		expect(svg).toHaveAttribute("role", "img");
	});

	it("renders polyline with correct number of points", () => {
		render(<MiniSparkline data={[1, 3, 2, 5, 4]} />);
		const polyline = document.querySelector("polyline");
		expect(polyline).toBeInTheDocument();
		// 5 data points = 5 coordinate pairs
		const points = polyline?.getAttribute("points")?.trim().split(" ");
		expect(points).toHaveLength(5);
	});

	it("applies default dimensions (24x12)", () => {
		render(<MiniSparkline data={[1, 3, 2]} />);
		const svg = document.querySelector("svg");
		expect(svg).toHaveAttribute("width", "24");
		expect(svg).toHaveAttribute("height", "12");
	});

	it("supports custom dimensions", () => {
		render(<MiniSparkline data={[1, 2]} width={48} height={24} />);
		const svg = document.querySelector("svg");
		expect(svg).toHaveAttribute("width", "48");
		expect(svg).toHaveAttribute("height", "24");
	});

	it("applies positive trend color class by default", () => {
		render(<MiniSparkline data={[1, 2, 3]} trend="up" />);
		const svg = document.querySelector("svg");
		expect(svg?.className.baseVal).toContain("stroke-(--color-market-up)");
	});

	it("applies negative trend color class", () => {
		render(<MiniSparkline data={[3, 2, 1]} trend="down" />);
		const svg = document.querySelector("svg");
		expect(svg?.className.baseVal).toContain("stroke-(--color-market-down)");
	});

	it("applies neutral color class", () => {
		render(<MiniSparkline data={[2, 2, 2]} trend="neutral" />);
		const svg = document.querySelector("svg");
		expect(svg?.className.baseVal).toContain("stroke-(--color-foreground-muted)");
	});

	it("renders with aria-label", () => {
		render(<MiniSparkline data={[1, 3, 2]} aria-label="市场脉搏趋势" />);
		const svg = document.querySelector("svg");
		expect(svg).toHaveAttribute("aria-label", "市场脉搏趋势");
	});
});
```

**Step 2: 运行测试确认失败**

Run: `bun run test --run src/components/data-viz/mini-sparkline.test.tsx`
Expected: FAIL — module not found

**Step 3: 实现 MiniSparkline 组件**

创建 `src/components/data-viz/mini-sparkline.tsx`：

```tsx
interface MiniSparklineProps {
	readonly data: readonly number[];
	readonly width?: number;
	readonly height?: number;
	readonly trend?: "up" | "down" | "neutral";
	readonly ariaLabel?: string;
	readonly className?: string;
}

const TREND_COLORS = {
	up: "stroke-(--color-market-up)",
	down: "stroke-(--color-market-down)",
	neutral: "stroke-(--color-foreground-muted)",
} as const;

function toPoints(data: readonly number[], width: number, height: number, padding = 1): string {
	if (data.length === 0) return "";
	const min = Math.min(...data);
	const max = Math.max(...data);
	const range = max - min || 1;
	const xStep = (width - padding * 2) / (data.length - 1 || 1);
	return data
		.map((v, i) => {
			const x = padding + i * xStep;
			const y = height - padding - ((v - min) / range) * (height - padding * 2);
			return `${x},${y}`;
		})
		.join(" ");
}

function MiniSparkline({
	data,
	width = 24,
	height = 12,
	trend = "neutral",
	ariaLabel,
	className,
}: MiniSparklineProps) {
	const points = toPoints(data, width, height);

	return (
		<svg
			role="img"
			aria-label={ariaLabel}
			width={width}
			height={height}
			viewBox={`0 0 ${width} ${height}`}
			fill="none"
			className={[TREND_COLORS[trend], className].filter(Boolean).join(" ")}
		>
			<polyline
				points={points}
				strokeWidth="1.5"
				strokeLinecap="round"
				strokeLinejoin="round"
			/>
		</svg>
	);
}

export { MiniSparkline };
export type { MiniSparklineProps };
```

创建 `src/components/data-viz/index.ts`：

```typescript
export { MiniSparkline } from "./mini-sparkline";
export type { MiniSparklineProps } from "./mini-sparkline";
```

**Step 4: 运行测试确认通过**

Run: `bun run test --run src/components/data-viz/mini-sparkline.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add src/components/data-viz/
git commit -m "feat(data-viz): MiniSparkline component — 24x12px inline sparkline for collapsed sidebar"
```

---

## Task 3: 增强 HomeCollapsedSidebar 浓缩信息

**复杂度:** M | **依赖:** Task 2

**Files:**
- Modify: `src/features/home/components/home-collapsed-sidebar.tsx`
- Modify: `src/features/home/components/home-collapsed-sidebar.test.tsx`

**背景:** 当前 HomeCollapsedSidebar 的"市场脉搏"折叠项只有趋势 SVG 图标。设计文档要求增加 mini sparkline（24×12px），让折叠态保留信号级浓缩信息。

**Step 1: 写失败测试**

在 `home-collapsed-sidebar.test.tsx` 中新增：

```typescript
it("renders MiniSparkline in market pulse item when trendData provided", () => {
	render(<HomeCollapsedSidebar marketTrendData={[1, 3, 2, 5, 4]} />);
	const svg = document.querySelector("svg[role='img']");
	expect(svg).toBeInTheDocument();
});

it("renders market pulse item without sparkline when no trendData", () => {
	render(<HomeCollapsedSidebar />);
	const pulseButtons = screen.getAllByRole("button");
	// Market pulse button should still exist
	expect(pulseButtons[0]).toHaveAttribute("aria-label", "市场脉搏");
});
```

**Step 2: 运行测试确认失败**

Run: `bun run test --run src/features/home/components/home-collapsed-sidebar.test.tsx`
Expected: FAIL — `marketTrendData` prop 不存在

**Step 3: 更新 HomeCollapsedSidebar**

修改 `home-collapsed-sidebar.tsx`：
- 新增 `marketTrendData?: readonly number[]` prop
- 在市场脉搏 item 中，若有 `marketTrendData` 则渲染 `<MiniSparkline>` 替代固定趋势 SVG
- 无 `marketTrendData` 时保持原有 SVG 图标（向后兼容）

```tsx
import { MiniSparkline } from "@/components/data-viz";

interface HomeCollapsedSidebarProps {
	readonly alertCount?: number;
	readonly healthStatus?: "healthy" | "degraded" | "warning" | "critical";
	readonly marketTrendData?: readonly number[];
	readonly onExpand?: () => void;
	readonly className?: string;
}
```

市场脉搏 item 改为：

```tsx
{
	icon: marketTrendData ? (
		<MiniSparkline
			data={marketTrendData}
			trend={marketTrendData[marketTrendData.length - 1] >= marketTrendData[0] ? "up" : "down"}
			aria-label="市场脉搏趋势"
		/>
	) : (
		/* 原有固定趋势 SVG 保持不变 */
		<svg className="size-5" viewBox="0 0 20 20" fill="none">
			<path d="M2 14L6 10L10 13L14 6L18 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
		</svg>
	),
	"aria-label": "市场脉搏",
},
```

**Step 4: 运行测试确认通过**

Run: `bun run test --run src/features/home/components/home-collapsed-sidebar.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add src/features/home/components/home-collapsed-sidebar.tsx src/features/home/components/home-collapsed-sidebar.test.tsx
git commit -m "feat(home): v3 collapsed sidebar — MiniSparkline in market pulse item"
```

---

## Task 4: 增强 IntelligenceCollapsedSidebar 浓缩信息

**复杂度:** S | **依赖:** Task 2

**Files:**
- Modify: `src/features/markets/components/intelligence-collapsed-sidebar.tsx`
- Modify: `src/features/markets/components/intelligence-collapsed-sidebar.test.tsx`

**背景:** 类似 Task 3，为 Intelligence 页面折叠态增加筛选器激活数 badge（设计文档要求"筛选器激活数"）。

**Step 1: 写失败测试**

在 `intelligence-collapsed-sidebar.test.tsx` 中新增：

```typescript
it("renders filter active count badge when activeFilterCount > 0", () => {
	render(<IntelligenceCollapsedSidebar activeFilterCount={3} />);
	const badge = screen.getByText("3");
	expect(badge).toBeInTheDocument();
});

it("does not render filter badge when activeFilterCount is 0", () => {
	render(<IntelligenceCollapsedSidebar activeFilterCount={0} />);
	// Only target count badge should be visible (if any)
	expect(screen.queryByText("0")).not.toBeInTheDocument();
});
```

**Step 2: 运行测试确认失败**

Run: `bun run test --run src/features/markets/components/intelligence-collapsed-sidebar.test.tsx`
Expected: FAIL — `activeFilterCount` prop 不存在

**Step 3: 更新 IntelligenceCollapsedSidebar**

新增 `activeFilterCount?: number` prop，增加筛选器 icon item：

```tsx
interface IntelligenceCollapsedSidebarProps {
	readonly targetCount?: number;
	readonly activeFilterCount?: number;
	readonly onExpand?: () => void;
	readonly className?: string;
}
```

在 items 数组中新增筛选器项（AI 解读和关联标的之间）：

```tsx
{
	icon: (
		<svg className="size-5" viewBox="0 0 20 20" fill="none">
			<path d="M3 5H17M3 10H17M3 15H10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
		</svg>
	),
	badge: activeFilterCount > 0 ? activeFilterCount : undefined,
	"aria-label": `筛选器 (${activeFilterCount} 激活)`,
},
```

**Step 4: 运行测试确认通过**

Run: `bun run test --run src/features/markets/components/intelligence-collapsed-sidebar.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add src/features/markets/components/intelligence-collapsed-sidebar.tsx src/features/markets/components/intelligence-collapsed-sidebar.test.tsx
git commit -m "feat(intelligence): v3 collapsed sidebar — active filter count badge"
```

---

## Task 5: L1/L2/L3 信息层级标注 — Home 页面组

**复杂度:** M | **依赖:** 无

**Files:**
- Modify: `src/features/home/components/home-page.tsx`
- Modify: `src/features/ai/components/ai-page.tsx`
- Modify: `src/features/platform/components/platform-page.tsx`

**背景:** 根据 P7 分配表，Home 组（Home、AI Overview、Platform）需要标注 L1/L2/L3 信息层级。标注方式：在各信息单元的容器上添加 `data-info-level="l1|l2|l3"` attribute。

**P7 分配表（Home 组）：**

| # | 页面 | L1 | L2 | L3 |
|---|------|----|----|-----|
| 1 | Home `/` | 5 | 3 | — |
| 2 | AI Overview `/ai` | 7 | 0 | — |
| 3 | Platform `/platform` | 3 | 3 | — |

**Step 1: 读取并理解 Home 页面结构**

Read: `src/features/home/components/home-page.tsx`
Read: `src/features/ai/components/ai-page.tsx`
Read: `src/features/platform/components/platform-page.tsx`

识别每个信息单元（Decision Banner、Priority Queue、Research Progress、Agent Findings 等）。

**Step 2: 在 Home 页面各信息单元容器上添加 `data-info-level`**

每个信息单元的顶层容器添加对应 attribute：

```tsx
{/* L1 — 首屏行动区 */}
<div data-info-level="l1" data-info-unit="decision-banner">
	<DecisionBanner />
</div>
<div data-info-level="l1" data-info-unit="priority-queue">
	<PriorityQueue />
</div>
{/* ... 其他 L1 项 */}

{/* L2 — 背景上下文区 */}
<div data-info-level="l2" data-info-unit="research-progress">
	<ResearchProgress />
</div>
{/* ... 其他 L2 项 */}
```

**Step 3: 对 AI Overview 和 Platform 页面做相同标注**

**Step 4: 写测试验证标注存在**

```typescript
it("marks decision-banner as L1 information level", () => {
	render(<HomePage />);
	const banner = document.querySelector("[data-info-unit='decision-banner']");
	expect(banner).toHaveAttribute("data-info-level", "l1");
});
```

**Step 5: Commit**

```bash
git add src/features/home/components/home-page.tsx src/features/ai/components/ai-page.tsx src/features/platform/components/platform-page.tsx
git commit -m "feat(v3): L1/L2/L3 info level annotations — Home group (Home, AI Overview, Platform)"
```

---

## Task 6: L1/L2/L3 信息层级标注 — Trading 页面组

**复杂度:** M | **依赖:** 无

**Files:**
- Modify: `src/features/trading/components/signals-page.tsx`
- Modify: `src/features/trading/components/orders-page.tsx`
- Modify: `src/features/trading/components/trading-page.tsx`
- Modify: `src/features/trading/components/risk-page.tsx`

**P7 分配表（Trading 组）：**

| # | 页面 | L1 | L2 | L3 |
|---|------|----|----|-----|
| 4 | Signals `/trading/signals` | 5 | 0 | 1 |
| 5 | Orders `/trading/orders` | 3 | 2 | 1 |
| 6 | Agent Console `/ai/agents` | 4 | 2 | — |
| 9 | Trading `/trading` | 5 | 4 | — |
| 10 | Risk Center `/trading/risk` | 4 | 2 | — |

**Step 1-4:** 同 Task 5 流程，为每个页面的信息单元添加 `data-info-level` + `data-info-unit` attribute。

**注意：** Signals 和 Orders 的 L3（signal-detail、order-detail）已在 Drawer 中实现（P5/P6），标注为 `data-info-level="l3"`。

**Step 5: Commit**

```bash
git add src/features/trading/components/signals-page.tsx src/features/trading/components/orders-page.tsx src/features/trading/components/trading-page.tsx src/features/trading/components/risk-page.tsx src/features/ai/components/agents-page.tsx
git commit -m "feat(v3): L1/L2/L3 info level annotations — Trading group (Signals, Orders, Trading, Risk, Agents)"
```

---

## Task 7: L1/L2/L3 信息层级标注 — Markets 页面组

**复杂度:** M | **依赖:** 无

**Files:**
- Modify: `src/features/markets/components/markets-page.tsx`
- Modify: `src/features/markets/components/intelligence-page.tsx`
- Modify: `src/features/markets/components/a-shares-page.tsx`
- Modify: `src/features/screener/components/screener-page.tsx`
- Modify: `src/features/markets/components/calendar-page.tsx`

**P7 分配表（Markets 组）：**

| # | 页面 | L1 | L2 | L3 |
|---|------|----|----|-----|
| 7 | Cross Market `/markets` | 4 | 3 | 4 |
| 8 | Intelligence `/markets/intelligence` | 4 | 1 | 4 |
| 13 | A-Shares `/markets/a-shares` | 4 | 3 | 1 |
| 14 | Screener `/markets/screener` | 3 | 2 | 3 |
| 15 | Calendar `/markets/calendar` | 3 | 1 | — |

**Step 1-4:** 同 Task 5 流程。

**Step 5: Commit**

```bash
git add src/features/markets/components/markets-page.tsx src/features/markets/components/intelligence-page.tsx src/features/markets/components/a-shares-page.tsx src/features/screener/components/screener-page.tsx src/features/markets/components/calendar-page.tsx
git commit -m "feat(v3): L1/L2/L3 info level annotations — Markets group (Cross Market, Intel, A-Shares, Screener, Calendar)"
```

---

## Task 8: L1/L2/L3 信息层级标注 — Research + Detail 页面组

**复杂度:** M | **依赖:** 无

**Files:**
- Modify: `src/features/research/components/research-page.tsx`
- Modify: `src/features/research/components/regime-page.tsx`
- Modify: `src/features/backtest/components/backtest-page.tsx`
- Modify: `src/features/research/components/factor-page.tsx`
- Modify: `src/features/instruments/components/instrument-hub-page.tsx`
- Modify: `src/features/strategy/components/strategy-detail-page.tsx`
- Modify: `src/features/strategy/components/strategy-page.tsx`
- Modify: `src/features/ai/components/copilot-page.tsx`

**P7 分配表（Research + Detail 组）：**

| # | 页面 | L1 | L2 | L3 |
|---|------|----|----|-----|
| 11 | Research `/research` | 4 | 2 | — |
| 12 | Regime `/research/regime` | 3 | 2 | — |
| 16 | Instrument Hub `/instruments/$id` | 4 | 2 | 7 |
| 17 | Backtest `/research/backtest/$id` | 4 | 2 | 3 |
| 18 | Factor `/research/factors/$id` | 4 | 2 | 1 |
| 19 | Strategy Detail `/strategies/$id` | 4 | 2 | 6 |
| 20 | Studio `/research/strategy-studio` | 4 | 2 | — |
| 21 | Copilot `/ai/copilot` | 3 | 1 | — |

**Step 1-4:** 同 Task 5 流程。

**注意：** 详情型页面（Instrument Hub、Strategy Detail、Backtest、Factor）L3 内容较多（6-7 项），这些内容应标注为 `data-info-level="l3"`，后续布局调整时考虑移入 Drawer 或 Tab。

**Step 5: Commit**

```bash
git add src/features/research/components/research-page.tsx src/features/research/components/regime-page.tsx src/features/backtest/components/backtest-page.tsx src/features/research/components/factor-page.tsx src/features/instruments/components/instrument-hub-page.tsx src/features/strategy/components/strategy-detail-page.tsx src/features/strategy/components/strategy-page.tsx src/features/ai/components/copilot-page.tsx
git commit -m "feat(v3): L1/L2/L3 info level annotations — Research + Detail group (8 pages)"
```

---

## Task 9: L3 内容布局调整 — 详情型页面

**复杂度:** L | **依赖:** Task 5-8

**Files:**
- Modify: `src/features/instruments/components/instrument-hub-page.tsx`
- Modify: `src/features/strategy/components/strategy-detail-page.tsx`
- Modify: `src/features/backtest/components/backtest-page.tsx`
- Modify: `src/features/screener/components/screener-page.tsx`
- Modify: `src/features/markets/components/markets-page.tsx`
- Modify: `src/features/markets/components/intelligence-page.tsx`

**背景:** P7 标注完成后，需要将 L3 信息单元从首屏平铺调整为按需展示。根据设计文档 D1 + D3：
- L3 内容需主动触发（点击/Drawer/Tab）
- 详情型页面 L3 内容多（Instrument Hub 7 项、Strategy Detail 6 项），需要 Drawer 或 Tab 收纳

**调整策略：**

| 页面 | L3 项数 | 调整方式 |
|------|---------|---------|
| Instrument Hub | 7 | 默认 Tab 显示 L1+L2，其余 Tab 收纳 L3 |
| Strategy Detail | 6 | 默认 Tab 显示 L1+L2，其余 Tab 收纳 L3 |
| Backtest | 3 | 前 4 项 L1+L2 平铺，后 3 项 L3 折叠 |
| Screener | 3 | 默认显示 L1+L2，L3 通过筛选/展开 |
| Cross Market | 4 | L3 区域通过 Tab 切换 |
| Intelligence | 4 | L3 区域通过 Drawer/Tab |

**Step 1: 逐页分析当前布局**

Read 各页面文件，识别哪些信息单元当前平铺但应属于 L3。

**Step 2: 制定每页具体调整方案**

对每个页面：
1. 列出当前平铺的所有信息单元
2. 对照 P7 分配表，标记哪些应从平铺移入 Tab/Drawer
3. 确定调整后的 DOM 结构

**Step 3: 实现调整**

对于需要 Tab 收纳的页面，使用 Radix Tabs 组件（shadcn/ui 已有）：

```tsx
<Tabs defaultValue="overview">
	<TabsList>
		<TabsTrigger value="overview">概览</TabsTrigger>
		<TabsTrigger value="details">详情</TabsTrigger>
	</TabsList>
	<TabsContent value="overview">
		{/* L1 + L2 信息单元 */}
	</TabsContent>
	<TabsContent value="details">
		{/* L3 信息单元 */}
	</TabsContent>
</Tabs>
```

**Step 4: 写测试验证布局调整**

```typescript
it("renders L3 items inside tabs content, not in default view", () => {
	render(<InstrumentHubPage />);
	// L1 items visible by default
	expect(screen.getByText("Price Header")).toBeInTheDocument();
	// L3 items not visible until tab switch
	expect(screen.queryByText("Full Order Book")).not.toBeInTheDocument();
});
```

**Step 5: Commit**

```bash
git add src/features/instruments/ src/features/strategy/ src/features/backtest/ src/features/screener/ src/features/markets/
git commit -m "feat(v3): L3 layout adjustment — move L3 info units to Tabs/Drawer on detail pages"
```

---

## Task 10: 一致性审查 + 测试全量验证

**复杂度:** M | **依赖:** Task 1-9

**Files:**
- Create: `src/features/shell/v3-compliance.test.tsx`

**背景:** 设计文档 D4 要求跨页面一致性。本任务验证所有 v3 实现的一致性。

**Step 1: 写一致性验证测试**

```typescript
describe("v3 Interaction Framework Compliance", () => {
	it("all collapsed sidebars use --width-sidebar-collapsed (56px)", () => {
		// 验证所有 CollapsedSidebar 组件使用一致的宽度 token
	});

	it("all drawers use --width-drawer (440px)", () => {
		// 验证所有 Drawer 实例使用一致的宽度 token
	});

	it("all pages with info level annotations have at least one L1 unit", () => {
		// 验证 L1 标注不为空
	});

	it("L3 units are not in the default visible view", () => {
		// 验证 L3 内容不在首屏平铺
	});
});
```

**Step 2: 运行全量测试**

Run: `bun run check`
Expected: ALL PASS（lint + type + test）

**Step 3: Commit**

```bash
git add src/features/shell/v3-compliance.test.tsx
git commit -m "test(v3): cross-page consistency compliance tests"
```

---

## 任务依赖图

```
Task 1 (Drawer Token)     ─── 独立
Task 2 (MiniSparkline)    ─── 独立
  ├── Task 3 (Home CollapsedSidebar 增强)
  └── Task 4 (Intelligence CollapsedSidebar 增强)
Task 5 (Home 组 L1/L2/L3 标注)  ─── 独立
Task 6 (Trading 组标注)          ─── 独立
Task 7 (Markets 组标注)          ─── 独立
Task 8 (Research+Detail 组标注)  ─── 独立
  └── Task 9 (L3 布局调整)  ─── 依赖 Task 5-8
      └── Task 10 (一致性验证)  ─── 依赖 Task 1-9
```

**可并行执行的任务组：**
- Group A: Task 1 + Task 2 + Task 5 + Task 6 + Task 7 + Task 8（全部独立）
- Group B: Task 3 + Task 4（依赖 Task 2）
- Group C: Task 9（依赖 Task 5-8）
- Group D: Task 10（依赖全部）
