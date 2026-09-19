import { describe, expect, it } from "vitest";
import type { BacktestNavPoint } from "../types";
import {
	alignedBenchmarkPoints,
	benchmarkGapCount,
	dateToUnix,
	drawdownBands,
	drawdownPoints,
	excessPoints,
	formatSignedPercent,
	normalizedNavPoints,
} from "./nav-chart-mapping";

const NAV: BacktestNavPoint[] = [
	{ tradeDate: "2026-01-05", nav: 1_000_000 },
	{ tradeDate: "2026-01-06", nav: 1_060_000 },
	{ tradeDate: "2026-01-07", nav: 980_000 },
	{ tradeDate: "2026-01-08", nav: 940_000 },
	{ tradeDate: "2026-01-09", nav: 1_070_000 },
	{ tradeDate: "2026-01-12", nav: 1_100_000 },
];

describe("normalizedNavPoints", () => {
	it("normalizes strategy NAV to a 1.0 base so benchmark overlay shares the scale", () => {
		const bars = normalizedNavPoints(NAV);
		expect(bars.map((bar) => bar.close)).toEqual([1, 1.06, 0.98, 0.94, 1.07, 1.1]);
	});

	it("returns empty for empty or zero-base series", () => {
		expect(normalizedNavPoints([])).toEqual([]);
		expect(normalizedNavPoints([{ tradeDate: "2026-01-05", nav: 0 }])).toEqual([]);
	});
});

describe("alignedBenchmarkPoints", () => {
	it("anchors on nav dates and maps missing benchmark days to whitespace gaps", () => {
		const navBars = normalizedNavPoints(NAV);
		const bars = alignedBenchmarkPoints(navBars, {
			dates: ["2026-01-05", "2026-01-06", "2026-01-09"],
			navs: [1.0, 1.02, 1.05],
		});
		expect(bars.map((bar) => bar.close)).toEqual([1.0, 1.02, null, null, 1.05, null]);
		expect(benchmarkGapCount(bars)).toBe(2);
	});

	it("drops benchmark dates outside the nav window instead of extending the time axis", () => {
		const navBars = normalizedNavPoints(NAV.slice(0, 2));
		const bars = alignedBenchmarkPoints(navBars, {
			dates: ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-30"],
			navs: [0.99, 1.0, 1.01, 1.2],
		});
		expect(bars.map((bar) => bar.close)).toEqual([1.0, 1.01]);
	});

	it("returns empty when either side is empty", () => {
		expect(alignedBenchmarkPoints([], { dates: ["2026-01-05"], navs: [1] })).toEqual([]);
		expect(alignedBenchmarkPoints(normalizedNavPoints(NAV), { dates: [], navs: [] })).toEqual([]);
	});
});

describe("excessPoints", () => {
	it("computes navNorm − benchNorm and keeps gaps where benchmark is missing", () => {
		const navBars = normalizedNavPoints(NAV.slice(0, 3));
		const benchBars = alignedBenchmarkPoints(navBars, {
			dates: ["2026-01-05", "2026-01-07"],
			navs: [1.0, 0.9],
		});
		const excess = excessPoints(navBars, benchBars);
		const [first, second, third] = excess.map((bar) => bar.close);
		expect(first).toBe(0);
		expect(second).toBeNull();
		expect(third).toBeCloseTo(0.08, 10);
	});
});

describe("drawdownPoints", () => {
	it("computes nav/peak − 1 underwater series matching backend drawdown semantics", () => {
		const bars = drawdownPoints(normalizedNavPoints(NAV));
		expect(bars.map((bar) => bar.close?.toFixed(4))).toEqual([
			"0.0000", // peak=1.0
			"0.0000", // new peak 1.06
			"-0.0755", // 0.98/1.06 − 1
			"-0.1132", // 0.94/1.06 − 1（最深）
			"0.0000", // 恢复并创新高 1.07
			"0.0000",
		]);
	});

	it("deepest point equals the report max drawdown magnitude for the same nav series", () => {
		// 后端 drawdown_analysis: max_dd = min(nav/peak − 1) → −0.113208…（%）
		const bars = drawdownPoints(normalizedNavPoints(NAV));
		const deepest = Math.min(...bars.map((bar) => bar.close ?? 0));
		expect(deepest * 100).toBeCloseTo(-11.3208, 3);
	});
});

describe("drawdownBands", () => {
	it("merges consecutive underwater days into one peak-to-recovery band", () => {
		const bands = drawdownBands(normalizedNavPoints(NAV));
		expect(bands).toHaveLength(1);
		expect(bands[0]).toMatchObject({
			from: dateToUnix("2026-01-07"),
			to: dateToUnix("2026-01-09"),
			color: "var(--chart-series-down)",
		});
	});

	it("extends an unrecovered drawdown to the last nav point", () => {
		const bands = drawdownBands(normalizedNavPoints(NAV.slice(0, 4)));
		expect(bands).toHaveLength(1);
		expect(bands[0]).toMatchObject({
			from: dateToUnix("2026-01-07"),
			to: dateToUnix("2026-01-08"),
		});
	});

	it("returns no bands for a monotonic rising series", () => {
		const rising = normalizedNavPoints([
			{ tradeDate: "2026-01-05", nav: 1 },
			{ tradeDate: "2026-01-06", nav: 2 },
			{ tradeDate: "2026-01-07", nav: 3 },
		]);
		expect(drawdownBands(rising)).toEqual([]);
	});
});

describe("readout formatters", () => {
	it("renders signed percent with the KPI numeric discipline", () => {
		expect(formatSignedPercent(0.0123)).toBe("+1.23%");
		expect(formatSignedPercent(-0.005)).toBe("−0.50%");
		expect(formatSignedPercent(0)).toBe("0.00%");
	});
});
