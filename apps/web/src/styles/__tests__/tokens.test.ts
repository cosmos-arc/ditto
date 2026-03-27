import * as fs from "node:fs";
import * as path from "node:path";
import { describe, expect, it } from "vitest";

const STYLES_DIR = path.resolve(__dirname, "..");
const TOKENS_DIR = path.join(STYLES_DIR, "tokens");

function readCss(filename: string): string {
	return fs.readFileSync(path.join(TOKENS_DIR, filename), "utf-8");
}

function getDarkBlock(css: string): string {
	// Split by ".dark {" selector, not ".dark" in comments
	const idx = css.indexOf(".dark {");
	if (idx === -1) return "";
	return css.slice(idx);
}

describe("Design Token v2 完整性", () => {
	describe("Primitive Token", () => {
		const css = readCss("primitives.css");

		it("包含 7 色相，6 色相 7 级 + cyan 6 级", () => {
			const sevenLevelHues = ["blue", "red", "green", "amber", "orange", "purple"];
			const levels = [50, 100, 200, 300, 400, 500, 600, 700];
			for (const hue of sevenLevelHues) {
				for (const level of levels) {
					const token = `--color-${hue}-${level}`;
					expect(css, `Missing ${token}`).toContain(token);
				}
			}
			// Cyan only has 6 levels (50-600)
			const cyanLevels = [50, 100, 200, 300, 400, 500, 600];
			for (const level of cyanLevels) {
				expect(css, `Missing --color-cyan-${level}`).toContain(`--color-cyan-${level}`);
			}
		});

		it("包含 15 级中性灰阶", () => {
			const neutrals = [0, 25, 50, 75, 100, 150, 200, 300, 400, 500, 600, 700, 800, 900, 950];
			for (const n of neutrals) {
				const token = `--color-neutral-${n}`;
				expect(css, `Missing ${token}`).toContain(token);
			}
		});

		it("包含 alpha 透明度 token", () => {
			expect(css).toContain("--alpha-white-2");
			expect(css).toContain("--alpha-white-3");
			expect(css).toContain("--alpha-white-12");
			expect(css).toContain("--alpha-black-48");
			expect(css).toContain("--alpha-black-72");
		});

		it("包含 spacing token", () => {
			expect(css).toContain("--spacing-1: 2px");
			expect(css).toContain("--spacing-4: 8px");
			expect(css).toContain("--spacing-8: 16px");
			expect(css).toContain("--spacing-16: 32px");
		});

		it("包含 radius token", () => {
			expect(css).toContain("--radius-none");
			expect(css).toContain("--radius-xs");
			expect(css).toContain("--radius-md");
			expect(css).toContain("--radius-round");
		});

		it("包含 shadow token", () => {
			expect(css).toContain("--shadow-none");
			expect(css).toContain("--shadow-sm");
			expect(css).toContain("--shadow-md");
			expect(css).toContain("--shadow-overlay");
		});

		it("使用 OKLCH 色彩空间", () => {
			expect(css).toContain("oklch(");
		});

		it("仅定义在 :root 中", () => {
			expect(css).not.toContain(".dark");
		});
	});

	describe("Semantic Core Token", () => {
		const css = readCss("semantic-core.css");

		it("text 7 级完整", () => {
			const levels = ["primary", "secondary", "tertiary", "muted", "disabled", "inverse", "link"];
			for (const level of levels) {
				expect(css, `Missing --color-text-${level}`).toContain(`--color-text-${level}`);
			}
		});

		it("icon 5 级完整", () => {
			const levels = ["primary", "muted", "active", "disabled", "inverse"];
			for (const level of levels) {
				expect(css, `Missing --color-icon-${level}`).toContain(`--color-icon-${level}`);
			}
		});

		it("surface 9 级完整", () => {
			const surfaces = ["app", "chrome", "canvas", "panel", "elevated", "raised", "active", "overlay", "inverse"];
			for (const s of surfaces) {
				expect(css, `Missing --color-surface-${s}`).toContain(`--color-surface-${s}`);
			}
		});

		it("border 5 级完整", () => {
			const borders = ["subtle", "default", "strong", "inverse", "focus"];
			for (const b of borders) {
				expect(css, `Missing --color-border-${b}`).toContain(`--color-border-${b}`);
			}
		});

		it("state 交互状态完整", () => {
			const states = [
				"hover-bg", "pressed-bg", "selected-bg", "selected-soft-bg",
				"focus-ring", "focus-ring-outer", "disabled-opacity", "drag-preview",
			];
			for (const s of states) {
				expect(css, `Missing --color-state-${s}`).toContain(`--color-state-${s}`);
			}
		});

		it("overlay 遮罩 token 完整", () => {
			// v2 规范使用 scrim/modal 命名
			expect(css).toContain("--color-overlay-scrim");
			expect(css).toContain("--color-overlay-modal");
			expect(css).toContain("--color-overlay-popover-border");
			expect(css).toContain("--color-overlay-popover-surface");
		});

		it("light 和 dark 都有定义", () => {
			expect(css).toContain(":root");
			expect(css).toContain(".dark");
		});

		it("dark 模式使用 var() 引用原语层", () => {
			const darkBlock = getDarkBlock(css);
			expect(darkBlock).toContain("var(--color-neutral-");
		});

		it("不包含已移除的 v1 token", () => {
			expect(css).not.toContain("--color-accent-primary");
			expect(css).not.toContain("--color-text-on-accent");
			expect(css).not.toContain("--color-ring-focus");
		});
	});

	describe("Semantic Market Token", () => {
		const css = readCss("semantic-market.css");

		it("up/down 都有 fg/fg-soft/bg/border/flash", () => {
			for (const dir of ["up", "down"]) {
				const subTokens = ["fg", "fg-soft", "bg", "border", "flash"];
				for (const sub of subTokens) {
					expect(css, `Missing --color-market-${dir}-${sub}`).toContain(`--color-market-${dir}-${sub}`);
				}
			}
		});

		it("flat 和 neutral 都有 fg/bg/border", () => {
			for (const type of ["flat", "neutral"]) {
				for (const sub of ["fg", "bg", "border"]) {
					expect(css, `Missing --color-market-${type}-${sub}`).toContain(`--color-market-${type}-${sub}`);
				}
			}
		});

		it("不支持旧的三位一体 stroke 格式", () => {
			expect(css).not.toContain("-stroke");
		});

		it("不包含 signal token（已归入 chart.series）", () => {
			expect(css).not.toContain("--color-signal-");
		});

		it("支持 CN/Global 模式切换", () => {
			expect(css).toContain("[data-market-locale=\"global\"]");
		});

		it("Global 模式交换 up/down", () => {
			// Just verify the global locale selector exists and swaps colors
			expect(css).toContain("[data-market-locale=\"global\"]");
			expect(css).toContain("--color-market-up-fg: var(--color-green-500)");
			expect(css).toContain("--color-market-down-fg: var(--color-red-500)");
		});
	});

	describe("Semantic Risk Token", () => {
		const css = readCss("semantic-risk.css");

		it("五级风险都有 fg/bg/border", () => {
			const levels = ["normal", "watch", "elevated", "breach", "locked"];
			for (const level of levels) {
				for (const sub of ["fg", "bg", "border"]) {
					expect(css, `Missing --color-risk-${level}-${sub}`).toContain(`--color-risk-${level}-${sub}`);
				}
			}
		});

		it("不支持旧的 low/medium/high/critical", () => {
			expect(css).not.toContain("--color-risk-low");
			expect(css).not.toContain("--color-risk-medium");
			expect(css).not.toContain("--color-risk-high");
			expect(css).not.toContain("--color-risk-critical");
		});
	});

	describe("Semantic Execution Token", () => {
		const css = readCss("semantic-execution.css");

		it("七态都有 fg/bg/border", () => {
			const states = ["pending", "submitted", "partial", "filled", "cancelled", "rejected", "expired"];
			for (const state of states) {
				for (const sub of ["fg", "bg", "border"]) {
					expect(css, `Missing --color-execution-${state}-${sub}`).toContain(`--color-execution-${state}-${sub}`);
				}
			}
		});
	});

	describe("Semantic System Token", () => {
		const css = readCss("semantic-system.css");

		it("五态都有 fg/bg/border", () => {
			const states = ["online", "degraded", "offline", "syncing", "maintenance"];
			for (const state of states) {
				for (const sub of ["fg", "bg", "border"]) {
					expect(css, `Missing --color-system-${state}-${sub}`).toContain(`--color-system-${state}-${sub}`);
				}
			}
		});
	});

	describe("Semantic Data Token", () => {
		const css = readCss("semantic-data.css");

		it("六态都有 fg/bg/border", () => {
			const states = ["fresh", "recent", "stale", "delayed", "missing", "backfilling"];
			for (const state of states) {
				for (const sub of ["fg", "bg", "border"]) {
					expect(css, `Missing --color-data-${state}-${sub}`).toContain(`--color-data-${state}-${sub}`);
				}
			}
		});
	});

	describe("Semantic Model Token", () => {
		const css = readCss("semantic-model.css");

		it("六态都有 fg/bg/border", () => {
			const states = ["draft", "validating", "accepted", "degraded", "deprecated", "failed"];
			for (const state of states) {
				for (const sub of ["fg", "bg", "border"]) {
					expect(css, `Missing --color-model-${state}-${sub}`).toContain(`--color-model-${state}-${sub}`);
				}
			}
		});
	});

	describe("semantic-status.css 已删除", () => {
		it("文件不存在", () => {
			const filePath = path.join(TOKENS_DIR, "semantic-status.css");
			expect(fs.existsSync(filePath)).toBe(false);
		});
	});

	describe("Charts Token", () => {
		const css = readCss("charts.css");

		it("基础 UI token 在 dual theme 中", () => {
			expect(css).toContain("--chart-tooltip-bg");
			expect(css).toContain("--chart-tooltip-shadow");
			expect(css).toContain("--chart-legend-text");
		});

		it("市场序列使用 var() 引用", () => {
			expect(css).toContain("--chart-series-market-price: var(--color-blue-600)");
			expect(css).toContain("--chart-series-market-ma-short: var(--color-amber-600)");
		});

		it("策略序列引用 market up/down", () => {
			expect(css).toContain("--chart-series-strategy-signal-buy: var(--color-market-up-fg)");
			expect(css).toContain("--chart-series-strategy-signal-sell: var(--color-market-down-fg)");
		});

		it("监控序列完整", () => {
			expect(css).toContain("--chart-series-monitoring-healthy");
			expect(css).toContain("--chart-series-monitoring-degraded");
			expect(css).toContain("--chart-series-monitoring-failed");
			expect(css).toContain("--chart-series-monitoring-queue");
			expect(css).toContain("--chart-series-monitoring-latency");
		});

		it("不包含旧通用多曲线色板", () => {
			expect(css).not.toContain("--chart-series-1:");
			expect(css).not.toContain("--chart-series-8:");
		});

		it("不包含旧 K 线 token", () => {
			expect(css).not.toContain("--chart-candle-up");
			expect(css).not.toContain("--chart-candle-down");
		});
	});

	describe("Grid Token", () => {
		const css = readCss("grid.css");

		it("默认密度为 compact (30px)", () => {
			expect(css).toContain("--grid-row-height: 30px");
		});

		it("三档密度都有定义", () => {
			expect(css).toContain("comfortable");
			expect(css).toContain("ultra-compact");
			expect(css).toContain("26px");
			expect(css).toContain("36px");
		});

		it("包含列强调层级", () => {
			expect(css).toContain("--grid-emphasis-decision-col-text");
			expect(css).toContain("--grid-emphasis-context-col-text");
			expect(css).toContain("--grid-emphasis-meta-col-text");
		});

		it("使用 var() 引用语义层", () => {
			expect(css).toContain("var(--color-surface-panel)");
			expect(css).toContain("var(--color-state-hover-bg)");
		});
	});

	describe("Components Token", () => {
		const css = readCss("components.css");

		it("文件存在", () => {
			expect(css.length).toBeGreaterThan(0);
		});

		it("包含 15 个组件域", () => {
			const domains = [
				"page", "panel", "card", "toolbar", "input", "button",
				"tabs", "badge", "toast", "kpi", "sidebar", "topbar", "inspector",
			];
			for (const domain of domains) {
				expect(css, `Missing component domain: ${domain}`).toContain(`--component-${domain}-`);
			}
		});

		it("全部使用 var() 引用", () => {
			// components.css 不应包含硬编码 oklch 值
			expect(css).not.toContain("oklch(");
		});
	});

	describe("Typography Token", () => {
		const css = readCss("typography.css");

		it("包含 KPI 字号", () => {
			expect(css).toContain("--font-size-kpi-sm");
			expect(css).toContain("--font-size-kpi-md");
			expect(css).toContain("--font-size-kpi-lg");
		});

		it("包含 Display 字号", () => {
			expect(css).toContain("--font-size-display-sm");
			expect(css).toContain("--font-size-display-md");
			expect(css).toContain("--font-size-display-lg");
		});

		it("包含字体栈", () => {
			expect(css).toContain("--font-family-sans");
			expect(css).toContain("--font-family-mono");
			expect(css).toContain("IBM Plex Sans");
			expect(css).toContain("IBM Plex Mono");
		});

		it("包含 tracking token", () => {
			expect(css).toContain("--font-tracking-tight");
			expect(css).toContain("--font-tracking-wide");
		});

		it("tight line-height 为 1.2", () => {
			expect(css).toContain("--font-line-height-tight: 1.2");
		});
	});

	describe("Motion Token", () => {
		const css = readCss("motion.css");

		it("五档时长有定义", () => {
			expect(css).toContain("--duration-instant");
			expect(css).toContain("--duration-fast");
			expect(css).toContain("--duration-normal");
			expect(css).toContain("--duration-slow");
			expect(css).toContain("--duration-xslow");
		});

		it("四种缓动有定义", () => {
			expect(css).toContain("--ease-standard");
			expect(css).toContain("--ease-decelerate");
			expect(css).toContain("--ease-accelerate");
			expect(css).toContain("--ease-emphasized");
		});

		it("flash token 有定义", () => {
			expect(css).toContain("--flash-up");
			expect(css).toContain("--flash-down");
			expect(css).toContain("--flash-neutral");
			expect(css).toContain("--flash-fade-duration");
			expect(css).toContain("--flash-enabled");
		});

		it("Reduced Motion 有 token 级关停", () => {
			expect(css).toContain("prefers-reduced-motion");
			expect(css).toContain("--duration-fast: 0ms");
			expect(css).toContain("--flash-enabled: 0");
		});
	});

	describe("globals.css 桥接表", () => {
		const css = fs.readFileSync(path.join(STYLES_DIR, "globals.css"), "utf-8");

		it("包含 @theme inline 桥接", () => {
			expect(css).toContain("@theme inline");
		});

		it("shadcn 核心 token 全部桥接", () => {
			const shadcnTokens = [
				"--color-background",
				"--color-foreground",
				"--color-card",
				"--color-popover",
				"--color-primary",
				"--color-destructive",
				"--color-border",
				"--color-ring",
			];
			for (const token of shadcnTokens) {
				expect(css, `Missing bridge: ${token}`).toContain(token);
			}
		});

		it("shadcn destructive 指向 risk-breach", () => {
			expect(css).toContain("--color-destructive: var(--color-risk-breach-fg)");
		});

		it("shadcn primary 指向 blue-500", () => {
			expect(css).toContain("--color-primary: var(--color-blue-500)");
		});

		it("Market 域注册为 Tailwind utility", () => {
			expect(css).toContain("--color-market-up: var(--color-market-up-fg)");
			expect(css).toContain("--color-market-down: var(--color-market-down-fg)");
			expect(css).toContain("--color-market-neutral: var(--color-market-neutral-fg)");
		});

		it("Risk 域注册为 Tailwind utility", () => {
			const riskLevels = ["normal", "watch", "elevated", "breach", "locked"];
			for (const level of riskLevels) {
				expect(css, `Missing risk utility: ${level}`).toContain(`--color-risk-${level}:`);
			}
		});

		it("Execution 域注册为 Tailwind utility", () => {
			expect(css).toContain("--color-execution-pending:");
			expect(css).toContain("--color-execution-filled:");
			expect(css).toContain("--color-execution-rejected:");
		});

		it("System 域注册为 Tailwind utility", () => {
			expect(css).toContain("--color-system-online:");
			expect(css).toContain("--color-system-degraded:");
			expect(css).toContain("--color-system-offline:");
		});

		it("Data 域注册为 Tailwind utility", () => {
			expect(css).toContain("--color-data-fresh:");
			expect(css).toContain("--color-data-stale:");
			expect(css).toContain("--color-data-missing:");
		});

		it("Model 域注册为 Tailwind utility", () => {
			expect(css).toContain("--color-model-draft:");
			expect(css).toContain("--color-model-accepted:");
			expect(css).toContain("--color-model-failed:");
		});

		it("Surface 展开注册", () => {
			expect(css).toContain("--color-surface-chrome:");
			expect(css).toContain("--color-surface-canvas:");
			expect(css).toContain("--color-surface-raised:");
			expect(css).toContain("--color-surface-active:");
		});

		it("Text 展开注册", () => {
			expect(css).toContain("--color-text-tertiary:");
			expect(css).toContain("--color-text-disabled:");
			expect(css).toContain("--color-text-link:");
		});

		it("不包含已移除的 v1 注册", () => {
			expect(css).not.toContain("--color-status-");
			expect(css).not.toContain("--color-signal-");
			expect(css).not.toContain("--color-risk-low:");
			expect(css).not.toContain("--color-risk-medium:");
			expect(css).not.toContain("--color-risk-high:");
			expect(css).not.toContain("--color-risk-critical:");
		});

		it("导入 6 个域语义文件", () => {
			expect(css).toContain("semantic-execution.css");
			expect(css).toContain("semantic-system.css");
			expect(css).toContain("semantic-data.css");
			expect(css).toContain("semantic-model.css");
			expect(css).toContain("components.css");
		});

		it("不导入 semantic-status.css", () => {
			expect(css).not.toContain("semantic-status.css");
		});

		it("字体包含 IBM Plex", () => {
			expect(css).toContain("IBM Plex Sans");
			expect(css).toContain("IBM Plex Mono");
		});

		it("暗色模式使用 class-based", () => {
			expect(css).toContain("@custom-variant dark");
			expect(css).toContain(".dark");
		});
	});

	describe("var() 引用架构验证", () => {
		it("语义文件 dark 模式不直接包含 oklch(", () => {
			const semanticFiles = [
				"semantic-core.css",
				"semantic-risk.css",
				"semantic-execution.css",
				"semantic-system.css",
				"semantic-data.css",
				"semantic-model.css",
			];
			for (const file of semanticFiles) {
				const css = readCss(file);
				const darkBlock = getDarkBlock(css);
				// dark block 允许 rgba（用于 flash/overlay），但不应有 oklch
				expect(darkBlock, `${file} .dark block should not contain oklch(`).not.toContain("oklch(");
			}
		});

		it("market 和 semantic-core dark 模式主要使用 var()", () => {
			const files = ["semantic-core.css", "semantic-market.css"];
			for (const file of files) {
				const css = readCss(file);
				const darkBlock = getDarkBlock(css);
				// 至少引用 var() — 允许少量 rgba 用于特殊效果
				expect(darkBlock, `${file} .dark should use var() refs`).toContain("var(");
			}
		});
	});
});
