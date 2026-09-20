import { describe, expect, it, vi } from "vitest";

const getMock = vi.fn<(path: string, init?: { params?: unknown }) => Promise<unknown>>();
vi.mock("@/api/transport", () => ({
	apiClient: { get: (path: string, init?: { params?: unknown }) => getMock(path, init) },
}));

import { fetchFactorEvaluationSeries } from "./factor-series";

function lastQuery(): Record<string, unknown> {
	const init = getMock.mock.calls.at(-1)?.[1] as { params?: { query?: Record<string, unknown> } } | undefined;
	return (init?.params?.query ?? {}) as Record<string, unknown>;
}

describe("fetchFactorEvaluationSeries", () => {
	it("targets the factor evaluation-series path with the factor id", async () => {
		getMock.mockResolvedValue({});
		await fetchFactorEvaluationSeries("momentum_20");
		expect(getMock).toHaveBeenCalledWith(
			"/api/v1/research/factors/{factor_id}/evaluation-series",
			expect.objectContaining({
				params: expect.objectContaining({ path: { factor_id: "momentum_20" } }),
			}),
		);
	});

	it("sends only the parameters that are present (optional keys stay absent)", async () => {
		getMock.mockResolvedValue({});
		await fetchFactorEvaluationSeries("momentum_20", { assetClass: "etf" });
		const query = lastQuery();
		expect(query).toEqual({ asset_class: "etf" });
	});

	it("passes every explicit parameter through to the query object", async () => {
		getMock.mockResolvedValue({});
		await fetchFactorEvaluationSeries("momentum_20", {
			version: 3,
			startDate: "2026-01-05",
			endDate: "2026-04-24",
			holdingPeriod: 10,
			nQuantiles: 4,
			rollingIrWindow: 30,
			assetClass: "stock",
			adj: "qfq",
		});
		expect(lastQuery()).toEqual({
			version: 3,
			start_date: "2026-01-05",
			end_date: "2026-04-24",
			holding_period: 10,
			n_quantiles: 4,
			rolling_ir_window: 30,
			asset_class: "stock",
			adj: "qfq",
		});
	});

	it("defaults to an empty query when no request fields are given", async () => {
		getMock.mockResolvedValue({});
		await fetchFactorEvaluationSeries("momentum_20", {});
		expect(lastQuery()).toEqual({});
	});
});
