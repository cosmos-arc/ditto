import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_STRATEGY_ID } from "../query-keys";
import { fetchFills, recordFill, type RecordFillRequest } from "../fills";

afterEach(() => {
	vi.unstubAllGlobals();
});

const recordFillPayload: RecordFillRequest = {
	fill_id: "fill-intent-510300-001",
	intent_id: "intent-510300",
	strategy_id: DEFAULT_STRATEGY_ID,
	trade_date: "2026-07-02",
	instrument_id: 510300,
	direction: "buy",
	quantity: 1000,
	fill_price: 4.32,
	fee: 1.5,
	slippage: 0.02,
	notes: "manual paper fill",
};

describe("fetchFills", () => {
	it("requests fill ledger with the default strategy id", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () =>
			new Response(
				JSON.stringify({
					data: [],
					pagination: { total: 0, limit: 0, offset: 0, has_more: false },
				}),
				{ status: 200, headers: { "Content-Type": "application/json" } },
			),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchFills()).resolves.toEqual([]);

		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/fills?strategy_id=seed_etf_industry_rotation",
			expect.objectContaining({ method: "GET" }),
		);
	});
});

describe("recordFill", () => {
	it("posts a manual paper fill and unwraps the response data", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () =>
			new Response(
				JSON.stringify({
					data: {
						...recordFillPayload,
						settlement_date: "2026-07-03",
					},
				}),
				{ status: 200, headers: { "Content-Type": "application/json" } },
			),
		);
		vi.stubGlobal("fetch", fetchMock);

		const fill = await recordFill(recordFillPayload);

		expect(fill.fill_id).toBe("fill-intent-510300-001");
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/fills",
			expect.objectContaining({
				method: "POST",
				body: JSON.stringify(recordFillPayload),
			}),
		);
	});
});
