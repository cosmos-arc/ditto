import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_STRATEGY_ID } from "../query-keys";
import { fetchDailyDecision } from "../daily-decision";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("fetchDailyDecision", () => {
	it("requests the live trade endpoint with the default ETF seed strategy id", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () =>
			new Response(
				JSON.stringify({
					data: {
						strategy_id: DEFAULT_STRATEGY_ID,
						trade_date: "2026-07-02",
						readiness: { status: "ready", reasons: [] },
						signal_intents: [],
						positions: [],
						deviation: null,
						pnl: null,
					},
				}),
				{ status: 200, headers: { "Content-Type": "application/json" } },
			),
		);
		vi.stubGlobal("fetch", fetchMock);

		const report = await fetchDailyDecision();

		expect(report.strategy_id).toBe(DEFAULT_STRATEGY_ID);
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/daily-decision?strategy_id=seed_etf_industry_rotation",
			expect.objectContaining({ method: "GET" }),
		);
	});

	it("passes an explicit trade date without adding /api in the hook path", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () =>
			new Response(
				JSON.stringify({
					data: {
						strategy_id: "seed_etf_trend_swing",
						trade_date: "2026-07-01",
						readiness: { status: "blocked", reasons: ["no signal intents available"] },
						signal_intents: [],
						positions: [],
						deviation: null,
						pnl: null,
					},
				}),
				{ status: 200, headers: { "Content-Type": "application/json" } },
			),
		);
		vi.stubGlobal("fetch", fetchMock);

		await fetchDailyDecision({
			strategyId: "seed_etf_trend_swing",
			tradeDate: "2026-07-01",
		});

		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/daily-decision?strategy_id=seed_etf_trend_swing&trade_date=2026-07-01",
			expect.objectContaining({ method: "GET" }),
		);
	});
});
