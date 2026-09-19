import { useEffect, useState } from "react";
import { cssColorToEngineColor, CHART_FALLBACK_COLORS as FALLBACK_COLORS } from "@/lib/oklch";
import type { FreshnessBucket } from "./chart-data";

/**
 * Chart Cockpit 主题解析：canvas 渲染需要具体色值，这里在运行时把 chart 层
 * token（`--chart-*` / `--data-freshness-*`）解析成字符串/数值。
 * data-theme 或 data-market-region 变化时自动重解析（红涨绿跌 ↔ 绿涨红跌即时生效）。
 * 解析失败（无 CSS 环境，如 jsdom）时回落到与 :root 一致的暗色镜像。
 */

export type ChartTheme = {
	readonly background: string;
	readonly grid: string;
	readonly crosshair: string;
	readonly axisText: string;
	readonly axisLine: string;
	readonly up: string;
	readonly down: string;
	readonly neutral: string;
	readonly freshness: Readonly<Record<FreshnessBucket, number>>;
	/** 把任意 chart 层 token 引用（如 "var(--chart-run-1)"）解析为具体色值。 */
	readonly resolve: (cssVar: string) => string;
};

const FALLBACK_FRESHNESS: Readonly<Record<FreshnessBucket, number>> = {
	live: 1,
	recent: 0.85,
	aging: 0.65,
	stale: 0.4,
	expired: 0.25,
};

const THEME_COLOR_TOKENS = {
	background: "var(--chart-bg)",
	grid: "var(--chart-grid)",
	crosshair: "var(--chart-crosshair)",
	axisText: "var(--chart-axis-text)",
	axisLine: "var(--chart-axis-line)",
	up: "var(--chart-series-up)",
	down: "var(--chart-series-down)",
	neutral: "var(--chart-series-neutral)",
} as const;

const FRESHNESS_TOKENS: Readonly<Record<FreshnessBucket, string>> = {
	live: "--data-freshness-live",
	recent: "--data-freshness-recent",
	aging: "--data-freshness-aging",
	stale: "--data-freshness-stale",
	expired: "--data-freshness-expired",
};

function fallbackFor(cssVar: string): string {
	return FALLBACK_COLORS[cssVar] ?? FALLBACK_COLORS[`var(${cssVar})`] ?? cssVar;
}

/**
 * lightweight-charts 的颜色解析器只接受 rgb()/rgba()/#hex，不接受 oklch()
 * 等 CSS 颜色串；浏览器 getComputedStyle 又会把 token 序列化成 oklch()。
 * 用 src/lib/oklch 的标准 OKLab 矩阵换算成引擎可解析的形式。
 */
function toEngineColor(color: string): string {
	return cssColorToEngineColor(color) ?? color;
}

/** jsdom/无 CSS 环境的暗色镜像（与解析后的 :root 对齐，chart-fallback-sync 测试守护）。 */
export const FALLBACK_CHART_THEME: ChartTheme = {
	background: fallbackFor("var(--chart-bg)"),
	grid: fallbackFor("var(--chart-grid)"),
	crosshair: fallbackFor("var(--chart-crosshair)"),
	axisText: fallbackFor("var(--chart-axis-text)"),
	axisLine: fallbackFor("var(--chart-axis-line)"),
	up: fallbackFor("var(--chart-series-up)"),
	down: fallbackFor("var(--chart-series-down)"),
	neutral: fallbackFor("var(--chart-series-neutral)"),
	freshness: FALLBACK_FRESHNESS,
	resolve: (cssVar) => fallbackFor(cssVar),
};

let sharedProbe: HTMLElement | null = null;

function probeElement(): HTMLElement | null {
	if (typeof document === "undefined") return null;
	if (!sharedProbe?.isConnected) {
		sharedProbe = document.createElement("div");
		sharedProbe.style.display = "none";
		document.body.appendChild(sharedProbe);
	}
	return sharedProbe;
}

function computesColor(probe: HTMLElement, cssVar: string): string | null {
	// 与一个必然非法的值对比：token 缺失/环境不支持 var() 时两者同为继承色
	//（非法赋值被 CSSOM 忽略，内联色保持清除状态，回落到继承色）。
	probe.style.color = "";
	probe.style.color = "not-a-color";
	const inherited = getComputedStyle(probe).color;
	probe.style.color = "";
	probe.style.color = cssVar;
	const computed = getComputedStyle(probe).color;
	if (!computed || computed === inherited) return null;
	return computed;
}

/** 每次主题解析重建的缓存：主题属性变化后旧值不残留。 */
let colorCache = new Map<string, string>();

function makeResolver(probe: HTMLElement): (cssVar: string) => string {
	return (cssVar: string): string => {
		const cached = colorCache.get(cssVar);
		if (cached !== undefined) return cached;
		const computed = computesColor(probe, cssVar);
		// 计算值必须能解析成颜色（jsdom 会把 var() 原样返回，不是颜色）；
		// 否则走与 :root 对齐的回退表。
		const color =
			computed !== null && cssColorToEngineColor(computed) !== null ? toEngineColor(computed) : fallbackFor(cssVar);
		colorCache.set(cssVar, color);
		return color;
	};
}

export function resolveChartTheme(): ChartTheme {
	const probe = probeElement();
	if (!probe) return FALLBACK_CHART_THEME;
	colorCache = new Map();
	const resolve = makeResolver(probe);
	const freshness = Object.fromEntries(
		(Object.keys(FRESHNESS_TOKENS) as FreshnessBucket[]).map((bucket) => {
			probe.style.opacity = "";
			probe.style.opacity = `var(${FRESHNESS_TOKENS[bucket]})`;
			const parsed = Number.parseFloat(getComputedStyle(probe).opacity ?? "");
			return [bucket, Number.isFinite(parsed) ? parsed : FALLBACK_FRESHNESS[bucket]];
		}),
	) as Record<FreshnessBucket, number>;
	return {
		background: resolve(THEME_COLOR_TOKENS.background),
		grid: resolve(THEME_COLOR_TOKENS.grid),
		crosshair: resolve(THEME_COLOR_TOKENS.crosshair),
		axisText: resolve(THEME_COLOR_TOKENS.axisText),
		axisLine: resolve(THEME_COLOR_TOKENS.axisLine),
		up: resolve(THEME_COLOR_TOKENS.up),
		down: resolve(THEME_COLOR_TOKENS.down),
		neutral: resolve(THEME_COLOR_TOKENS.neutral),
		freshness,
		resolve,
	};
}

/** 订阅 html 上 data-theme / data-market-region 变化，主题即时重解析。 */
export function useChartTheme(): ChartTheme {
	const [theme, setTheme] = useState<ChartTheme>(resolveChartTheme);
	useEffect(() => {
		const observer = new MutationObserver(() => {
			setTheme(resolveChartTheme());
		});
		observer.observe(document.documentElement, {
			attributes: true,
			attributeFilter: ["data-theme", "data-market-region"],
		});
		return () => observer.disconnect();
	}, []);
	return theme;
}
