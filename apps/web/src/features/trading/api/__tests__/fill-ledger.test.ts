import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchFillLedger } from "../fill-ledger";

type TestFill = {
	readonly fill_id: string;
	readonly intent_id: string;
	readonly strategy_id: string;
	readonly trade_date: string;
	readonly instrument_id: number;
	readonly direction: "buy" | "sell";
	readonly quantity: number;
	readonly fill_price: number;
	readonly fee: number;
	readonly slippage: number;
	readonly notes: string;
	readonly settlement_date: string;
};

type TestAdjustment = {
	readonly adjustment_id: string;
	readonly fill_id: string;
	readonly adjustment_type: "void" | "replace";
	readonly replacement_fill_id: string | null;
	readonly reason: string;
	readonly created_at: string;
};

function makeFill(fillId: string, overrides: Partial<TestFill> = {}): TestFill {
	return {
		fill_id: fillId,
		intent_id: "intent-001",
		strategy_id: "strategy-r1",
		trade_date: "2026-07-02",
		instrument_id: 510300,
		direction: "buy",
		quantity: 100,
		fill_price: 4.32,
		fee: 1,
		slippage: 0,
		notes: "broker evidence",
		settlement_date: "2026-07-03",
		...overrides,
	};
}

function makeReplaceAdjustment(
	fillId: string,
	replacementFillId: string,
	overrides: Partial<TestAdjustment> = {},
): TestAdjustment {
	return {
		adjustment_id: `adjustment-${fillId}`,
		fill_id: fillId,
		adjustment_type: "replace",
		replacement_fill_id: replacementFillId,
		reason: "券商回单修正",
		created_at: "2026-07-16T09:31:00+08:00",
		...overrides,
	};
}

function installLedgerFetch(
	raw: readonly TestFill[],
	effective: readonly TestFill[],
	adjustments: readonly TestAdjustment[],
) {
	const fetchMock = vi.fn<typeof fetch>(async (input) => {
		const url = String(input);
		const data = url.includes("/fill-adjustments") ? adjustments : url.includes("/fills/effective") ? effective : raw;
		return new Response(JSON.stringify({ data }), {
			status: 200,
			headers: { "Content-Type": "application/json" },
		});
	});
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("fetchFillLedger", () => {
	it("maps raw/effective fill DTOs to one auditable manual execution ledger", async () => {
		const fill = {
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
		};
		const fetchMock = vi.fn<typeof fetch>(async (input) => {
			const url = String(input);
			const data = url.includes("/fill-adjustments") ? [] : [fill];
			return new Response(JSON.stringify({ data }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			});
		});
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
					state: "effective",
					adjustment: null,
				},
			],
			issues: [],
		});
		expect(fetchMock).toHaveBeenCalledTimes(3);
	});

	it("keeps replaced originals visible while linking their immutable replacement evidence", async () => {
		const rawFills = [
			{
				fill_id: "fill-original",
				intent_id: "intent-001",
				strategy_id: "strategy-r1",
				trade_date: "2026-07-02",
				instrument_id: 510300,
				direction: "buy",
				quantity: 1000,
				fill_price: 4.32,
				fee: 1.5,
				slippage: 0.02,
				notes: "incorrect broker copy",
				settlement_date: "2026-07-03",
			},
			{
				fill_id: "fill-replacement",
				intent_id: "intent-001",
				strategy_id: "strategy-r1",
				trade_date: "2026-07-02",
				instrument_id: 510300,
				direction: "buy",
				quantity: 800,
				fill_price: 4.31,
				fee: 1.2,
				slippage: 0.01,
				notes: "broker-confirmed replacement",
				settlement_date: "2026-07-03",
			},
		];
		const adjustment = {
			adjustment_id: "adjustment-replace-001",
			fill_id: "fill-original",
			adjustment_type: "replace",
			replacement_fill_id: "fill-replacement",
			reason: "券商回单数量修正",
			created_at: "2026-07-16T09:31:00+08:00",
		};
		const fetchMock = vi.fn<typeof fetch>(async (input) => {
			const url = String(input);
			const data = url.includes("/fill-adjustments")
				? [adjustment]
				: url.includes("/fills/effective")
					? [rawFills[1]]
					: rawFills;
			return new Response(JSON.stringify({ data }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.fills).toHaveLength(2);
		expect(result.fills[0]).toMatchObject({
			id: "fill-original",
			state: "replaced",
			adjustment: {
				id: "adjustment-replace-001",
				reason: "券商回单数量修正",
				replacementFillId: "fill-replacement",
			},
		});
		expect(result.fills[1]).toMatchObject({
			id: "fill-replacement",
			state: "effective",
			adjustment: null,
		});
		expect(result.issues).toEqual([]);
	});

	it("marks contradictory or incomplete backend evidence unresolved instead of inventing a fill state", async () => {
		const rawFills = [
			{
				fill_id: "fill-effective-with-adjustment",
				intent_id: "intent-001",
				strategy_id: "strategy-r1",
				trade_date: "2026-07-02",
				instrument_id: 510300,
				direction: "buy",
				quantity: 100,
				fill_price: 4.32,
				fee: 1,
				slippage: 0,
				notes: "contradictory evidence",
				settlement_date: "2026-07-03",
			},
			{
				fill_id: "fill-missing-adjustment",
				intent_id: "intent-002",
				strategy_id: "strategy-r1",
				trade_date: "2026-07-02",
				instrument_id: 159915,
				direction: "sell",
				quantity: 200,
				fill_price: 2.68,
				fee: 1,
				slippage: 0,
				notes: "incomplete evidence",
				settlement_date: "2026-07-03",
			},
		];
		const adjustment = {
			adjustment_id: "adjustment-void-001",
			fill_id: rawFills[0].fill_id,
			adjustment_type: "void",
			replacement_fill_id: null,
			reason: "后台证据冲突",
			created_at: "2026-07-16T09:31:00+08:00",
		};
		const fetchMock = vi.fn<typeof fetch>(async (input) => {
			const url = String(input);
			const data = url.includes("/fill-adjustments")
				? [adjustment]
				: url.includes("/fills/effective")
					? [rawFills[0]]
					: rawFills;
			return new Response(JSON.stringify({ data }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.fills[0]).toMatchObject({
			state: "unresolved",
			consistencyIssue: "effective_with_adjustment",
			adjustment: { id: "adjustment-void-001" },
		});
		expect(result.fills[1]).toMatchObject({
			state: "unresolved",
			consistencyIssue: "missing_effective_and_adjustment",
			adjustment: null,
		});
		expect(result.issues.map((issue) => issue.code)).toEqual([
			"effective_with_adjustment",
			"missing_effective_and_adjustment",
		]);
	});

	it("fails closed and preserves adjustment evidence when a replacement fill is absent from raw history", async () => {
		const original = makeFill("fill-original");
		const adjustment = makeReplaceAdjustment(original.fill_id, "fill-missing");
		installLedgerFetch([original], [], [adjustment]);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.fills).toEqual([
			expect.objectContaining({
				id: "fill-original",
				state: "unresolved",
				consistencyIssue: "replacement_missing_raw",
				adjustment: expect.objectContaining({
					id: adjustment.adjustment_id,
					replacementFillId: "fill-missing",
				}),
			}),
		]);
		expect(result.issues).toEqual([
			{
				code: "replacement_missing_raw",
				fillId: "fill-original",
				relatedFillId: "fill-missing",
				adjustmentId: adjustment.adjustment_id,
				mismatchedFields: [],
			},
		]);
	});

	it("fails closed for a dangling replacement that is neither effective nor itself adjusted", async () => {
		const original = makeFill("fill-original");
		const replacement = makeFill("fill-replacement");
		const adjustment = makeReplaceAdjustment(original.fill_id, replacement.fill_id);
		installLedgerFetch([original, replacement], [], [adjustment]);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.fills).toEqual([
			expect.objectContaining({
				id: "fill-original",
				state: "unresolved",
				consistencyIssue: "replacement_not_resolved",
			}),
			expect.objectContaining({
				id: "fill-replacement",
				state: "unresolved",
				consistencyIssue: "replacement_not_resolved",
			}),
		]);
		expect(result.issues).toEqual([
			expect.objectContaining({
				code: "replacement_not_resolved",
				fillId: "fill-original",
				relatedFillId: "fill-replacement",
				adjustmentId: adjustment.adjustment_id,
			}),
		]);
	});

	it("accepts a coherent chained replacement whose intermediate fill has its own adjustment", async () => {
		const first = makeFill("fill-a");
		const second = makeFill("fill-b");
		const final = makeFill("fill-c");
		installLedgerFetch(
			[first, second, final],
			[final],
			[makeReplaceAdjustment(first.fill_id, second.fill_id), makeReplaceAdjustment(second.fill_id, final.fill_id)],
		);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.issues).toEqual([]);
		expect(result.fills.map(({ id, state }) => ({ id, state }))).toEqual([
			{ id: "fill-a", state: "replaced" },
			{ id: "fill-b", state: "replaced" },
			{ id: "fill-c", state: "effective" },
		]);
	});

	it("fails closed on a cyclic replacement graph without looping or exposing an effective state", async () => {
		const first = makeFill("fill-cycle-a");
		const second = makeFill("fill-cycle-b");
		installLedgerFetch(
			[first, second],
			[],
			[makeReplaceAdjustment(first.fill_id, second.fill_id), makeReplaceAdjustment(second.fill_id, first.fill_id)],
		);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.issues).toEqual([
			expect.objectContaining({
				code: "replacement_cycle",
				fillId: "fill-cycle-a",
				relatedFillId: "fill-cycle-b",
			}),
		]);
		expect(result.fills.map(({ id, state }) => ({ id, state }))).toEqual([
			{ id: "fill-cycle-a", state: "unresolved" },
			{ id: "fill-cycle-b", state: "unresolved" },
		]);
	});

	it("surfaces an orphan adjustment as top-level unresolved evidence instead of dropping it", async () => {
		const adjustment = makeReplaceAdjustment("fill-orphan", "fill-missing");
		installLedgerFetch([], [], [adjustment]);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.fills).toEqual([]);
		expect(result.issues).toEqual([
			{
				code: "orphan_adjustment",
				fillId: "fill-orphan",
				relatedFillId: "fill-missing",
				adjustmentId: adjustment.adjustment_id,
				mismatchedFields: [],
			},
		]);
	});

	it("does not classify strategy-wide adjustments outside a date-filtered raw window as orphaned", async () => {
		const inRange = makeFill("fill-in-range", { trade_date: "2026-07-16" });
		const outOfRangeAdjustment = makeReplaceAdjustment("fill-before-window", "fill-before-window-replacement");
		installLedgerFetch([inRange], [inRange], [outOfRangeAdjustment]);

		const result = await fetchFillLedger({
			strategyId: "strategy-r1",
			startDate: "2026-07-16",
			endDate: "2026-07-16",
		});

		expect(result.issues).toEqual([]);
		expect(result.fills).toEqual([expect.objectContaining({ id: "fill-in-range", state: "effective" })]);
	});

	it("does not invent a missing-replacement conflict when a replacement falls outside the date window", async () => {
		const original = makeFill("fill-in-range-original", { trade_date: "2026-07-16" });
		const adjustment = makeReplaceAdjustment(original.fill_id, "fill-outside-window-replacement");
		installLedgerFetch([original], [], [adjustment]);

		const result = await fetchFillLedger({
			strategyId: "strategy-r1",
			startDate: "2026-07-16",
			endDate: "2026-07-16",
		});

		expect(result.issues).toEqual([]);
		expect(result.fills).toEqual([expect.objectContaining({ id: original.fill_id, state: "replaced" })]);
	});

	it("still rejects a replace adjustment with no replacement identity inside a date window", async () => {
		const original = makeFill("fill-in-range-invalid", { trade_date: "2026-07-16" });
		const adjustment = makeReplaceAdjustment(original.fill_id, "unused", { replacement_fill_id: null });
		installLedgerFetch([original], [], [adjustment]);

		const result = await fetchFillLedger({
			strategyId: "strategy-r1",
			startDate: "2026-07-16",
			endDate: "2026-07-16",
		});

		expect(result.issues).toEqual([
			expect.objectContaining({
				code: "replacement_missing_raw",
				fillId: original.fill_id,
				relatedFillId: null,
			}),
		]);
		expect(result.fills).toEqual([expect.objectContaining({ id: original.fill_id, state: "unresolved" })]);
	});

	it("synthesizes an unresolved ledger row for an effective fill missing from raw history", async () => {
		const ghost = makeFill("fill-ghost");
		installLedgerFetch([], [ghost], []);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.fills).toEqual([
			expect.objectContaining({
				id: "fill-ghost",
				state: "unresolved",
				consistencyIssue: "ghost_effective",
				adjustment: null,
			}),
		]);
		expect(result.issues).toEqual([
			expect.objectContaining({
				code: "ghost_effective",
				fillId: "fill-ghost",
				relatedFillId: null,
				adjustmentId: null,
			}),
		]);
	});

	it("fails closed when a replacement changes correction-chain identity", async () => {
		const original = makeFill("fill-original");
		const replacement = makeFill("fill-replacement", {
			intent_id: "intent-other",
			strategy_id: "strategy-other",
			instrument_id: 159915,
			direction: "sell",
		});
		const adjustment = makeReplaceAdjustment(original.fill_id, replacement.fill_id);
		installLedgerFetch([original, replacement], [replacement], [adjustment]);

		const result = await fetchFillLedger({ strategyId: "strategy-r1" });

		expect(result.fills.map(({ id, state }) => ({ id, state }))).toEqual([
			{ id: "fill-original", state: "unresolved" },
			{ id: "fill-replacement", state: "unresolved" },
		]);
		expect(result.issues).toEqual([
			expect.objectContaining({
				code: "replacement_identity_mismatch",
				fillId: "fill-original",
				relatedFillId: "fill-replacement",
				adjustmentId: adjustment.adjustment_id,
				mismatchedFields: ["intent_id", "strategy_id", "instrument_id", "direction"],
			}),
		]);
	});
});
