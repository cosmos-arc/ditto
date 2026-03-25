import * as fs from "node:fs";
import * as path from "node:path";
import { describe, expect, it } from "vitest";

const STYLES_DIR = path.resolve(__dirname, "..");
const TOKENS_DIR = path.join(STYLES_DIR, "tokens");

function readCss(filename: string): string {
	return fs.readFileSync(path.join(TOKENS_DIR, filename), "utf-8");
}

describe("Design Token 完整性", () => {
	describe("Primitive Token", () => {
		const css = readCss("primitives.css");

		it("包含 6 色相 × 6 级彩色色阶", () => {
			const hues = ["red", "green", "amber", "blue", "violet", "purple"];
			const levels = [50, 100, 200, 300, 400, 500];
			for (const hue of hues) {
				for (const level of levels) {
					const token = `--color-${hue}-${level}`;
					expect(css, `Missing ${token}`).toContain(token);
				}
			}
		});

		it("包含 12 级中性灰阶", () => {
			for (let i = 0; i <= 11; i++) {
				const token = `--color-neutral-${i}`;
				expect(css, `Missing ${token}`).toContain(token);
			}
		});
	});

	describe("Semantic Core Token", () => {
		const css = readCss("semantic-core.css");

		it("light 和 dark 主题都有 surface 层级", () => {
			const surfaces = ["app", "panel", "elevated", "hover", "selected"];
			for (const s of surfaces) {
				const token = `--color-surface-${s}`;
				expect(css, `Missing ${token} in light`).toContain(token);
			}
			expect(css).toContain(".dark");
		});

		it("light 和 dark 主题都有 text 层级", () => {
			expect(css).toContain("--color-text-primary");
			expect(css).toContain("--color-text-secondary");
			expect(css).toContain("--color-text-muted");
		});

		it("包含 ring-focus", () => {
			expect(css).toContain("--color-ring-focus");
		});
	});

	describe("Semantic Market Token", () => {
		const css = readCss("semantic-market.css");

		it("涨跌色都有 fg/bg/stroke 三位一体", () => {
			for (const dir of ["up", "down", "flat"]) {
				for (const type of ["fg", "bg", "stroke"]) {
					const token = `--color-market-${dir}-${type}`;
					expect(css, `Missing ${token}`).toContain(token);
				}
			}
		});

		it("信号色都有 fg/bg/stroke 三位一体", () => {
			for (const sig of ["buy", "sell", "hold"]) {
				for (const type of ["fg", "bg", "stroke"]) {
					const token = `--color-signal-${sig}-${type}`;
					expect(css, `Missing ${token}`).toContain(token);
				}
			}
		});
	});

	describe("Semantic Risk Token", () => {
		const css = readCss("semantic-risk.css");

		it("四个风险等级都有 fg/bg/stroke", () => {
			const levels = ["low", "medium", "high", "critical"];
			for (const level of levels) {
				for (const type of ["fg", "bg", "stroke"]) {
					const token = `--color-risk-${level}-${type}`;
					expect(css, `Missing ${token}`).toContain(token);
				}
			}
		});
	});

	describe("Charts Token", () => {
		const css = readCss("charts.css");

		it("8 色通用多曲线色板有定义", () => {
			for (let i = 1; i <= 8; i++) {
				expect(css, `Missing --chart-series-${i}`).toContain(
					`--chart-series-${i}`,
				);
			}
		});

		it("K 线涨跌色有定义", () => {
			expect(css).toContain("--chart-candle-up");
			expect(css).toContain("--chart-candle-down");
		});

		it("策略序列色有定义", () => {
			expect(css).toContain("--chart-strategy-nav");
			expect(css).toContain("--chart-benchmark");
			expect(css).toContain("--chart-excess-return");
		});
	});

	describe("Grid Token", () => {
		const css = readCss("grid.css");

		it("默认密度为 compact (32px)", () => {
			expect(css).toContain("--grid-row-height: 32px");
		});

		it("三档密度都有定义", () => {
			expect(css).toContain("comfortable");
			expect(css).toContain("ultra-compact");
			expect(css).toContain("26px");
			expect(css).toContain("40px");
		});
	});

	describe("Typography Token", () => {
		const css = readCss("typography.css");

		it("字号阶梯完整", () => {
			const sizes = [
				"page-title",
				"section-header",
				"body-default",
				"body-compact",
				"label",
				"caption",
				"kpi",
			];
			for (const size of sizes) {
				expect(css, `Missing --font-size-${size}`).toContain(
					`--font-size-${size}`,
				);
			}
		});
	});

	describe("Motion Token", () => {
		const css = readCss("motion.css");

		it("三档时长有定义", () => {
			expect(css).toContain("--duration-fast");
			expect(css).toContain("--duration-normal");
			expect(css).toContain("--duration-slow");
		});

		it("闪烁策略有定义", () => {
			expect(css).toContain("--motion-flash-enabled");
		});

		it("Reduced Motion 有 token 级关停", () => {
			expect(css).toContain("prefers-reduced-motion");
			expect(css).toContain("--duration-fast: 0ms");
			expect(css).toContain("--motion-flash-enabled: 0");
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

		it("Ditto 语义色注册为 Tailwind utility", () => {
			const dittoTokens = [
				"--color-market-up",
				"--color-market-down",
				"--color-risk-low",
				"--color-risk-critical",
				"--color-status-success",
				"--color-status-error",
				"--color-signal-buy",
				"--color-signal-sell",
			];
			for (const token of dittoTokens) {
				expect(css, `Missing utility: ${token}`).toContain(token);
			}
		});

		it("暗色模式使用 class-based", () => {
			expect(css).toContain("@custom-variant dark");
			expect(css).toContain(".dark");
		});
	});
});
