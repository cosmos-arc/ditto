import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchDailyDecision, fetchDailyDecisionV2 } from "../daily-decision";
import { DEFAULT_STRATEGY_ID, tradingKeys } from "../query-keys";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("fetchDailyDecisionV2", () => {
	it("isolates cached decisions by strategy, signal date, and account", () => {
		expect(tradingKeys.dailyDecision("strategy-r1", "2026-07-16", "paper-a")).toEqual([
			"trading",
			"daily-decision",
			"strategy-r1",
			"2026-07-16",
			"paper-a",
		]);
		expect(tradingKeys.dailyDecision("strategy-r1", "2026-07-16", "paper-a")).not.toEqual(
			tradingKeys.dailyDecision("strategy-r1", "2026-07-16", "paper-b"),
		);
	});

	it("requests the persisted package decision contract", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: {
							identity: { strategy_id: DEFAULT_STRATEGY_ID, signal_date: "2026-07-02" },
							readiness: { status: "review", reason_codes: ["NO_REBALANCE"] },
							data: {},
							run_package: { outcome: "completed", no_rebalance: true },
							account_positions: { positions: [] },
							actions: [],
							execution_review: {},
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		const report = await fetchDailyDecisionV2();

		expect(report.readiness.status).toBe("review");
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/daily-decision/v2?strategy_id=seed_etf_industry_rotation",
			expect.objectContaining({ method: "GET" }),
		);
	});

	it("uses the explicit strategy and account execution scope from the URL", async () => {
		const originalUrl = `${window.location.pathname}${window.location.search}`;
		window.history.replaceState(null, "", "/trading?strategy_id=seed_etf_trend_swing&account_id=paper-r1");
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: {
							identity: { strategy_id: "seed_etf_trend_swing", account_id: "paper-r1" },
							readiness: { status: "blocked", reason_codes: ["EOD_RUN_MISSING"] },
							data: {},
							run_package: { outcome: "missing" },
							account_positions: { positions: [] },
							actions: [],
							execution_review: {},
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		try {
			await fetchDailyDecisionV2();
			expect(fetchMock).toHaveBeenCalledWith(
				"/api/v1/trade/daily-decision/v2?strategy_id=seed_etf_trend_swing&account_id=paper-r1",
				expect.objectContaining({ method: "GET" }),
			);
		} finally {
			window.history.replaceState(null, "", originalUrl);
		}
	});
});

describe("fetchDailyDecision", () => {
	it("requests the live trade endpoint with the default ETF seed strategy id", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
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
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
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
