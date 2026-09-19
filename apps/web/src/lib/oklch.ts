/**
 * OKLCH → sRGB 转换（OKLab 标准矩阵）。
 * 单一权威实现：浏览器图表引擎（lightweight-charts 只接受 rgb()/rgba()/#hex）
 * 与 scripts/token-utils.mjs 的对比度审计共用同一套矩阵与 gamma。
 */

export type OklchColor = {
	readonly l: number;
	readonly c: number;
	readonly h: number;
	readonly alpha: number;
};

const OKLCH_PATTERN = /^oklch\(\s*([\d.]+)(%)?\s+([\d.]+)(%)?\s+([\d.-]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/u;

/** 解析 `oklch(L C H [/ A])`；L 支持百分比（%）形式。不匹配返回 null。 */
export function parseOklchColor(value: string): OklchColor | null {
	const match = value.trim().match(OKLCH_PATTERN);
	if (!match) return null;
	const l = match[2] ? Number.parseFloat(match[1]!) / 100 : Number.parseFloat(match[1]!);
	const c = Number.parseFloat(match[3]!);
	const h = Number.parseFloat(match[5]!);
	const alphaRaw = match[6] ?? "1";
	const alpha = alphaRaw.endsWith("%") ? Number.parseFloat(alphaRaw) / 100 : Number.parseFloat(alphaRaw);
	if (![l, c, h, alpha].every((part) => Number.isFinite(part))) return null;
	return { l, c, h, alpha };
}

function clamp01(value: number): number {
	return value < 0 ? 0 : value > 1 ? 1 : value;
}

/** OKLCH → sRGB（0–1 浮点，gamut 截断）。 */
export function oklchToRgbUnit(l: number, c: number, h: number): [number, number, number] {
	const hRad = (h * Math.PI) / 180;
	const a = c * Math.cos(hRad);
	const b = c * Math.sin(hRad);

	const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
	const m = l + -0.1055613458 * a + -0.0638541728 * b;
	const s = l + -0.0894841775 * a + -1.291485548 * b;

	const l3 = l_ * l_ * l_;
	const m3 = m * m * m;
	const s3 = s * s * s;

	const r = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3;
	const g = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3;
	const b2 = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3;

	const gamma = (channel: number) => (channel <= 0.0031308 ? 12.92 * channel : 1.055 * channel ** (1 / 2.4) - 0.055);

	return [gamma(clamp01(r)), gamma(clamp01(g)), gamma(clamp01(b2))];
}

const RGB_PATTERN = /^rgba?\(\s*([\d.]+)\s*[,\s]\s*([\d.]+)\s*[,\s]\s*([\d.]+)(?:\s*[,\s]\s*([\d.]+))?\s*\)$/iu;

/**
 * 把 CSS 颜色串转成图表引擎可解析的形式（`#rrggbb` / `rgba(r, g, b, a)`）。
 * 支持 oklch()（含 alpha 与百分比亮度）与 rgb()/rgba()/#hex 透传；
 * 无法解析时返回 null，由调用方决定回退。
 */
export function cssColorToEngineColor(value: string): string | null {
	const trimmed = value.trim();
	const oklch = parseOklchColor(trimmed);
	if (oklch) {
		const [r, g, b] = oklchToRgbUnit(oklch.l, oklch.c, oklch.h);
		const to255 = (channel: number) => Math.round(channel * 255);
		if (oklch.alpha >= 1) {
			const hex = (channel: number) => to255(channel).toString(16).padStart(2, "0");
			return `#${hex(r)}${hex(g)}${hex(b)}`;
		}
		return `rgba(${to255(r)}, ${to255(g)}, ${to255(b)}, ${oklch.alpha})`;
	}
	const rgb = trimmed.match(RGB_PATTERN);
	if (rgb) {
		const alpha = rgb[4] !== undefined ? Number.parseFloat(rgb[4]) : 1;
		return `rgba(${Number.parseFloat(rgb[1]!)}, ${Number.parseFloat(rgb[2]!)}, ${Number.parseFloat(rgb[3]!)}, ${alpha})`;
	}
	if (/^#[0-9a-f]{6}$/iu.test(trimmed) || /^#[0-9a-f]{8}$/iu.test(trimmed)) {
		return trimmed.toLowerCase();
	}
	return null;
}

/** 给引擎色注入透明度（canvas 渲染需要）；无法解析时原样返回。 */
export function withAlpha(color: string, alpha: number): string {
	const clamped = Math.min(1, Math.max(0, alpha));
	const engine = cssColorToEngineColor(color);
	if (!engine) return color;
	if (engine.startsWith("#")) {
		const r = Number.parseInt(engine.slice(1, 3), 16);
		const g = Number.parseInt(engine.slice(3, 5), 16);
		const b = Number.parseInt(engine.slice(5, 7), 16);
		return `rgba(${r}, ${g}, ${b}, ${clamped})`;
	}
	const parts = engine.slice("rgba(".length, -1).split(/[,\s]+/u);
	parts[3] = String(clamped);
	return `rgba(${parts.join(", ")})`;
}

/**
 * 图表主题回退色：与 tokens-data-viz.css :root（暗色）解析后的最终值逐一对齐
 * （scripts/chart-fallback-sync.test.ts 守护同步）。token 调整而未同步时该测试
 * 会失败。仅用于无 CSS 环境（jsdom）与 token 解析失败时兜底。
 */
export const CHART_FALLBACK_COLORS: Readonly<Record<string, string>> = {
	"var(--chart-bg)": "#0c0f13",
	"var(--chart-grid)": "rgba(255, 255, 255, 0.06)",
	"var(--chart-crosshair)": "rgba(255, 255, 255, 0.25)",
	"var(--chart-axis-text)": "#7f8286",
	"var(--chart-axis-line)": "#212326",
	"var(--chart-series-up)": "#eb6268",
	"var(--chart-series-down)": "#53ae77",
	"var(--chart-series-neutral)": "#81878d",
};
