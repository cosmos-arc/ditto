import { afterEach, describe, expect, it, vi } from "vitest";
import {
	fetchEffectiveFills,
	fetchFillAdjustments,
	fetchFills,
	type RecordFillRequest,
	recordFill,
	replaceFill,
	voidFill,
} from "../fills";
import { DEFAULT_STRATEGY_ID } from "../query-keys";

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
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
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

	it("reads effective fills and append-only adjustment evidence from separate endpoints", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(JSON.stringify({ data: [] }), {
					status: 200,
					headers: { "Content-Type": "application/json" },
				}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchEffectiveFills({ strategyId: "strategy-r1" })).resolves.toEqual([]);
		await expect(
			fetchFillAdjustments({ strategyId: "strategy-r1", fillId: "fill-001", intentId: "intent-001" }),
		).resolves.toEqual([]);

		expect(fetchMock).toHaveBeenNthCalledWith(
			1,
			"/api/v1/trade/fills/effective?strategy_id=strategy-r1",
			expect.objectContaining({ method: "GET" }),
		);
		expect(fetchMock).toHaveBeenNthCalledWith(
			2,
			"/api/v1/trade/fill-adjustments?strategy_id=strategy-r1&fill_id=fill-001&intent_id=intent-001",
			expect.objectContaining({ method: "GET" }),
		);
	});
});

describe("recordFill", () => {
	it("posts a manual paper fill and unwraps the response data", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
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

describe("append-only fill correction", () => {
	it("posts a void event with a stable adjustment id and reason", async () => {
		const payload = { adjustment_id: "adjustment-void-001", reason: "录入了错误数量" };
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: {
							...payload,
							fill_id: "fill-001",
							adjustment_type: "void",
							replacement_fill_id: null,
							created_at: "2026-07-16T09:30:00+08:00",
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(voidFill("fill-001", payload)).resolves.toMatchObject({
			adjustment_id: "adjustment-void-001",
			adjustment_type: "void",
		});
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/fills/fill-001/void",
			expect.objectContaining({ method: "POST", body: JSON.stringify(payload) }),
		);
	});

	it("posts a replacement fill and its linked adjustment as one correction request", async () => {
		const payload = {
			adjustment_id: "adjustment-replace-001",
			replacement_fill_id: "fill-001-replacement",
			trade_date: "2026-07-03",
			quantity: 800,
			fill_price: 4.31,
			reason: "券商回单数量修正",
			fee: 1.2,
			slippage: 0.01,
			notes: "manual correction",
		};
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: {
							adjustment_id: payload.adjustment_id,
							fill_id: "fill-001",
							adjustment_type: "replace",
							replacement_fill_id: payload.replacement_fill_id,
							reason: payload.reason,
							created_at: "2026-07-16T09:31:00+08:00",
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(replaceFill("fill-001", payload)).resolves.toMatchObject({
			adjustment_id: "adjustment-replace-001",
			replacement_fill_id: "fill-001-replacement",
		});
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/trade/fills/fill-001/replace",
			expect.objectContaining({ method: "POST", body: JSON.stringify(payload) }),
		);
	});
});
