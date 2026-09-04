import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchComparisonAttribution } from "../comparison";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("fetchComparisonAttribution", () => {
	it("requests comparison metrics with strategy id and run id", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: {
							backtest_return: 0.08,
							actual_return: 0.071,
							return_diff: -0.009,
							return_diff_bps: -90,
							backtest_sharpe: 1.3,
							actual_sharpe: 1.1,
							backtest_total_cost: 12,
							actual_total_cost: 18,
							cost_drag_bps: 6,
							nav_correlation: 0.98,
							max_nav_diff_bps: 42,
							avg_daily_tracking_error_bps: 12.5,
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchComparisonAttribution({ runId: "run-001" })).resolves.toEqual({
			rows: [
				{ label: "收益差异", value: "-90.0 bps", detail: "actual 7.10% vs backtest 8.00%" },
				{ label: "成本拖累", value: "6.0 bps", detail: "actual cost 18.00 vs backtest cost 12.00" },
				{ label: "跟踪误差", value: "12.5 bps", detail: "NAV corr 0.9800, max diff 42.0 bps" },
				{ label: "Sharpe 差异", value: "-0.20", detail: "actual 1.10 vs backtest 1.30" },
			],
		});

		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/manual/comparison?strategy_id=seed_etf_industry_rotation&run_id=run-001",
			expect.objectContaining({ method: "GET" }),
		);
	});
});
