/**
 * HEX → OKLCH 转换脚本
 * 将 v2 设计规范中的所有 HEX 值转换为 OKLCH 格式
 * 用法: bun scripts/convert-hex-to-oklch.mts
 */
import { oklch, parse, formatCss } from "culori";

function hexToOklch(hex: string): string {
	const color = parse(hex);
	if (!color) throw new Error(`Cannot parse: ${hex}`);
	const oklchColor = oklch(color);
	return formatCss(oklchColor);
}

// ── v2 Design Token HEX values ──

const colors: Record<string, string> = {
	// Neutral (15 levels)
	"neutral-0": "#0B0F14",
	"neutral-25": "#0E1319",
	"neutral-50": "#10161D",
	"neutral-75": "#131A22",
	"neutral-100": "#17202A",
	"neutral-150": "#1B2530",
	"neutral-200": "#22303D",
	"neutral-300": "#2B3A49",
	"neutral-400": "#385062",
	"neutral-500": "#4A657B",
	"neutral-600": "#6C8195",
	"neutral-700": "#91A3B5",
	"neutral-800": "#B7C4D1",
	"neutral-900": "#DDE6EE",
	"neutral-950": "#F5F8FB",

	// Blue (7 levels)
	"blue-50": "#0F1E3A",
	"blue-100": "#132952",
	"blue-200": "#1D3D78",
	"blue-300": "#3159A6",
	"blue-400": "#4C78D0",
	"blue-500": "#5F8FF5",
	"blue-600": "#82A9FF",
	"blue-700": "#A9C3FF",

	// Cyan (6 levels)
	"cyan-50": "#0D1C22",
	"cyan-100": "#11303A",
	"cyan-200": "#185067",
	"cyan-300": "#23748F",
	"cyan-400": "#2E9AB8",
	"cyan-500": "#46B8D8",
	"cyan-600": "#73CAE3",

	// Red (7 levels)
	"red-50": "#2A1418",
	"red-100": "#341C21",
	"red-200": "#442126",
	"red-300": "#6D313A",
	"red-400": "#8D424B",
	"red-500": "#D85C5C",
	"red-600": "#E06A6A",
	"red-700": "#F0B6B6",

	// Green (7 levels)
	"green-50": "#122019",
	"green-100": "#16281F",
	"green-200": "#17271F",
	"green-300": "#244731",
	"green-400": "#2D6144",
	"green-500": "#43A36F",
	"green-600": "#58B77A",
	"green-700": "#9BD4AF",

	// Amber (7 levels)
	"amber-50": "#211A10",
	"amber-100": "#2C2315",
	"amber-200": "#2D2417",
	"amber-300": "#4B3B22",
	"amber-400": "#6D5730",
	"amber-500": "#D0A04A",
	"amber-600": "#D9A85B",
	"amber-700": "#E8C98B",

	// Orange (7 levels)
	"orange-50": "#24160F",
	"orange-100": "#312116",
	"orange-200": "#352416",
	"orange-300": "#5A3725",
	"orange-400": "#7B4C33",
	"orange-500": "#E38B57",
	"orange-600": "#E28D5D",
	"orange-700": "#F1C3A0",

	// Purple (7 levels)
	"purple-50": "#1F1827",
	"purple-100": "#241F31",
	"purple-200": "#27212D",
	"purple-300": "#43365A",
	"purple-400": "#5B4B7A",
	"purple-500": "#B497E7",
	"purple-600": "#C4B0EC",
	"purple-700": "#DDD1F6",
};

console.log("/* HEX → OKLCH Conversion Results */\n");

for (const [name, hex] of Object.entries(colors)) {
	const oklchStr = hexToOklch(hex);
	console.log(`  --color-${name}: ${oklchStr};  /* ${hex} */`);
}
