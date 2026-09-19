import { describe, expect, it } from "vitest";
import { CHART_FALLBACK_COLORS, cssColorToEngineColor, oklchToRgbUnit, parseOklchColor, withAlpha } from "./oklch";

describe("parseOklchColor", () => {
	it("parses plain, alpha, and percent forms", () => {
		expect(parseOklchColor("oklch(0.5 0.1 30)")).toEqual({ l: 0.5, c: 0.1, h: 30, alpha: 1 });
		expect(parseOklchColor("oklch(0.5 0.1 30 / 0.4)")).toEqual({ l: 0.5, c: 0.1, h: 30, alpha: 0.4 });
		expect(parseOklchColor("oklch(100% 0 0)")).toEqual({ l: 1, c: 0, h: 0, alpha: 1 });
		expect(parseOklchColor("oklch(0.5 0.1 30 / 40%)")).toEqual({ l: 0.5, c: 0.1, h: 30, alpha: 0.4 });
	});

	it("rejects non-oklch or malformed values", () => {
		expect(parseOklchColor("rgb(1 2 3)")).toBeNull();
		expect(parseOklchColor("oklch(not a color)")).toBeNull();
		expect(parseOklchColor("")).toBeNull();
	});
});

describe("oklchToRgbUnit", () => {
	it("maps anchors deterministically with gamut clamping", () => {
		for (const channel of oklchToRgbUnit(1, 0, 0)) {
			expect(channel).toBeCloseTo(1, 6);
		}
		expect(oklchToRgbUnit(0, 0, 0)).toEqual([0, 0, 0]);
		const [r, g, b] = oklchToRgbUnit(0.67, 0.17, 20);
		expect(r).toBeGreaterThan(g);
		expect(r).toBeGreaterThan(b);
		for (const channel of [r, g, b]) {
			expect(channel).toBeGreaterThanOrEqual(0);
			expect(channel).toBeLessThanOrEqual(1);
		}
	});
});

describe("cssColorToEngineColor", () => {
	it("converts oklch tokens to engine-parsable hex/rgba", () => {
		expect(cssColorToEngineColor("oklch(0.67 0.17 20)")).toBe("#eb6268");
		expect(cssColorToEngineColor("oklch(0.68 0.12 155 / 0.55)")).toBe("rgba(83, 174, 119, 0.55)");
		expect(cssColorToEngineColor("oklch(1 0 0)")).toBe("#ffffff");
	});

	it("passes through rgb()/rgba()/hex and rejects unknown syntax", () => {
		expect(cssColorToEngineColor("rgb(10 20 30)")).toBe("rgba(10, 20, 30, 1)");
		expect(cssColorToEngineColor("rgba(10, 20, 30, 0.5)")).toBe("rgba(10, 20, 30, 0.5)");
		expect(cssColorToEngineColor("#AABBCC")).toBe("#aabbcc");
		expect(cssColorToEngineColor("var(--chart-run-1)")).toBeNull();
	});
});

describe("withAlpha", () => {
	it("emits engine-parsable rgba for oklch, hex, and rgba inputs", () => {
		expect(withAlpha("oklch(0.67 0.17 20)", 0.55)).toBe("rgba(235, 98, 104, 0.55)");
		expect(withAlpha("#eb6268", 0.4)).toBe("rgba(235, 98, 104, 0.4)");
		expect(withAlpha("rgba(10, 20, 30, 0.9)", 0.25)).toBe("rgba(10, 20, 30, 0.25)");
	});

	it("clamps alpha and passes unknown values through", () => {
		expect(withAlpha("#eb6268", 2)).toBe("rgba(235, 98, 104, 1)");
		expect(withAlpha("paint-me", 0.5)).toBe("paint-me");
	});
});

describe("CHART_FALLBACK_COLORS", () => {
	it("keeps one engine-parsable fallback per chart theme token", () => {
		for (const value of Object.values(CHART_FALLBACK_COLORS)) {
			expect(cssColorToEngineColor(value)).not.toBeNull();
		}
	});
});
