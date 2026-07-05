import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchFillLedger } from "../fill-ledger";

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("fetchFillLedger", () => {
	it("maps backend fill DTOs to manual execution ledger rows", async () => {
		const fetchMock = vi.fn<typeof fetch>(async () =>
			new Response(
				JSON.stringify({
					data: [
						{
							fill_id: "fill-001",
							intent_id: "intent-001",
							strategy_id: "seed_etf_industry_rotation",
							trade_date: "2026-07-02",
							instrument_id: 510300,
							direction: "buy",
							quantity: 1000,
							fill_price: 4.32,
							fee: 1.5,
							slippage: 0.02,
							notes: "manual paper fill",
							settlement_date: "2026-07-03",
						},
					],
				}),
				{ status: 200, headers: { "Content-Type": "application/json" } },
			),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchFillLedger()).resolves.toEqual({
			fills: [
				{
					id: "fill-001",
					intentId: "intent-001",
					tradeDate: "2026-07-02",
					instrument: "#510300",
					direction: "BUY",
					quantity: 1000,
					fillPrice: 4.32,
					fee: 1.5,
					slippage: 0.02,
					notes: "manual paper fill",
				},
			],
		});
	});
});
