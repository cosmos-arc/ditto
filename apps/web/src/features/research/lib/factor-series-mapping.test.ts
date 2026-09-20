import { describe, expect, it } from "vitest";
import type { FactorEvaluationSeriesResponse } from "../api/factor-series";
import { heatmapBucket, icSeries, monthlyIcRows, quantileSeries } from "./factor-series-mapping";

const RESPONSE: FactorEvaluationSeriesResponse = {
	factor_id: "momentum_20",
	factor_version: 1,
	holding_period: 5,
	n_quantiles: 5,
	rolling_ir_window: 20,
	period_start: "2026-01-05",
	period_end: "2026-02-02",
	n_dates: 3,
	dates: ["2026-01-05", "2026-01-06", "2026-01-07"],
	ic: [0.1, null, -0.2],
	rolling_ir: [null, null, 1.5],
	quantile_nav: [
		{ quantile: 1, nav: [0.99, 0.98, 0.97] },
		{ quantile: 5, nav: [1.01, 1.02, 1.03] },
	],
	ls_nav: [1.0, 1.01, 1.02],
	monthly_ic: [
		{ year: 2026, month: 1, mean_ic: 0.05, days: 20 },
		{ year: 2026, month: 3, mean_ic: -0.02, days: 22 },
		{ year: 2025, month: 12, mean_ic: 0.0, days: 10 },
	],
};

describe("icSeries", () => {
	it("maps IC to the left axis and rolling IR to the right with gap semantics", () => {
		const specs = icSeries(RESPONSE);
		expect(specs.map((spec) => spec.id)).toEqual(["ic", "rolling_ir"]);
		expect(specs[0]).toMatchObject({ priceScaleId: "left" });
		expect(specs[1]).toMatchObject({ priceScaleId: "right" });
		// null（IC 缺失日 / IR warm-up）保留为断口
		expect(specs[0]?.bars.map((bar) => bar.close)).toEqual([0.1, null, -0.2]);
		expect(specs[1]?.bars.map((bar) => bar.close)).toEqual([null, null, 1.5]);
	});
});

describe("quantileSeries", () => {
	it("renders quantile tokens plus the LS spread line", () => {
		const specs = quantileSeries(RESPONSE);
		expect(specs.map((spec) => spec.id)).toEqual(["q_1", "q_5", "ls_spread"]);
		expect(specs[0]).toMatchObject({ color: "var(--chart-quantile-1)" });
		expect(specs[1]).toMatchObject({ color: "var(--chart-quantile-5)" });
		expect(specs[2]).toMatchObject({ color: "var(--chart-ls-spread)" });
	});
});

describe("monthlyIcRows", () => {
	it("builds year rows with a 12-month grid and null holes", () => {
		const rows = monthlyIcRows(RESPONSE);
		expect(rows.map((row) => row.year)).toEqual([2025, 2026]);
		const y2026 = rows[1]!;
		expect(y2026.cells).toHaveLength(12);
		expect(y2026.cells[0]).toMatchObject({ month: 1, meanIc: 0.05, days: 20 });
		expect(y2026.cells[1]?.meanIc).toBeNull();
		expect(y2026.cells[2]).toMatchObject({ month: 3, meanIc: -0.02 });
	});
});

describe("heatmapBucket", () => {
	it("buckets by sign and magnitude with a none hole", () => {
		expect(heatmapBucket(null)).toBe("none");
		expect(heatmapBucket(0.001)).toBe("up-1");
		expect(heatmapBucket(-0.001)).toBe("down-1");
		expect(heatmapBucket(0.05)).toBe("up-3");
		expect(heatmapBucket(-0.05)).toBe("down-3");
	});

	it("caps the magnitude bucket at level 5", () => {
		expect(heatmapBucket(0.4)).toBe("up-5");
		expect(heatmapBucket(-0.9)).toBe("down-5");
	});
});
