import { afterEach, describe, expect, it, vi } from "vitest";
import {
	correctManualAccountEvent,
	createManualAccount,
	fetchManualAccountLedger,
	type ManualEventBody,
	type ReverseManualEventBody,
	recordManualAccountEvent,
	reverseManualAccountEvent,
} from "../manual-accounts";
import {
	createPaperAccount,
	createPaperSession,
	fetchPaperAccountLedger,
	fetchPaperSession,
	type OperatePaperOrderBody,
	operatePaperOrder,
	pausePaperSession,
	reconcilePaperSession,
	recoverPaperSession,
} from "../paper-accounts";

afterEach(() => {
	vi.unstubAllGlobals();
});

function respondWith(data: unknown, status = 200): typeof fetch {
	return vi.fn<typeof fetch>(async () =>
		Promise.resolve(
			new Response(JSON.stringify({ data }), {
				status,
				headers: { "Content-Type": "application/json" },
			}),
		),
	);
}

const manualAccount = {
	account_id: "manual-a",
	kind: "manual",
	name: "Main",
	opened_at: "2026-09-04T00:00:00Z",
	currency: "CNY",
};

const incompleteManualEvent = {
	account_id: "manual-a",
	account_kind: "manual",
	currency: "CNY",
	event_id: "event-1",
	event_hash: "account-event:sha256:event-1",
};

const manualEventBody = {
	actor: "local-user",
	attachment_refs: [],
	event_type: "buy",
	fees: "5",
	gross_amount: "1000",
	idempotency_key: "manual-event-1",
	instrument_id: 510300,
	note: "buy",
	price: "10",
	quantity: "100",
	settlement_date: "2026-09-05",
	tax: "0",
	trade_date: "2026-09-04",
} satisfies ManualEventBody;

const reverseManualEventBody = {
	actor: "local-user",
	idempotency_key: "manual-reversal-1",
	note: "reverse",
	reverses_event_id: "event-0",
	settlement_date: "2026-09-05",
	trade_date: "2026-09-04",
} satisfies ReverseManualEventBody;

const manualResponseEvent = {
	account_id: "manual-a",
	account_kind: "manual",
	actor: "local-user",
	attachment_refs: [],
	corrects_event_id: null,
	currency: "CNY",
	event_hash: "account-event:sha256:event-1",
	event_id: "event-1",
	event_type: "buy",
	external_reference: null,
	fees: "5",
	gross_amount: "1000",
	idempotency_key: manualEventBody.idempotency_key,
	instrument_id: 510300,
	net_cash: "-1005",
	note: "buy",
	price: "10",
	quantity: "100",
	recorded_at: "2026-09-04T10:00:00Z",
	replacement_event_type: null,
	reverses_event_id: null,
	settlement_date: "2026-09-05",
	source: "manual_entry",
	tax: "0",
	trade_date: "2026-09-04",
} as const;

const paperAccountBody = {
	account_id: "paper-a",
	currency: "CNY",
	idempotency_key: "paper-account-1",
	initial_cash: "100000",
	name: "Paper",
	opened_at: "2026-09-04T00:00:00Z",
	trade_date: "2026-09-04",
} as const;

const paperSessionBody = {
	account_id: "paper-a",
	idempotency_key: "paper-session-1",
	session_id: "paper-s-1",
	start_immediately: true,
	strategy_id: "strategy-1",
	trade_date: "2026-09-04",
} as const;

const paperOrderBody = {
	assumption: { assumption_id: "default-v1", reference_price_field: "close", slippage_bps: 1, version: 1 },
	available_quantity: 0,
	decision_at: "2026-09-04T09:30:00Z",
	execution_at: "2026-09-04T10:00:00Z",
	idempotency_key: "operate-1",
	instrument_id: 510300,
	market: {
		amount: 1000000,
		close: 10,
		dataset_id: "etf_daily",
		high: 10.1,
		is_suspended: false,
		low: 9.9,
		observed_at: "2026-09-04T10:00:00Z",
		open: 10,
		prev_close: 9.9,
		publication_cutoff: "2026-09-04T10:00:00Z",
		source: "test",
		source_snapshot_id: "snapshot-1",
		volume: 100000,
	},
	order_id: "order-1",
	order_type: "market",
	position_quantity: 0,
	quantity: 100,
	rules: {
		asset_class: "etf",
		board_segment: "fund",
		commission_rate: 0.0003,
		currency: "CNY",
		exchange: "SSE",
		lifecycle_state: "listed",
		lot_size: 100,
		min_commission: 5,
		multiplier: 1,
		price_limit_pct: 0.1,
		settlement_cycle: 1,
		stamp_duty_rate: 0,
		tick_size: 0.001,
		transfer_fee_rate: 0,
	},
	settlement_date: "2026-09-05",
	side: "buy",
	trade_date: "2026-09-04",
} satisfies OperatePaperOrderBody;

const paperExecution = {
	status: "created",
	execution_id: "execution-1",
	idempotency_key: "operate-1",
	request_hash: "a".repeat(64),
	order_id: "order-1",
	order_status: "filled",
	reality_status: "filled",
	reason: null,
	ledger_event_id: "ledger-event-1",
	fill: {
		assumption_hash: "assumption-1",
		commission: 5,
		direction: "buy",
		event_time: "2026-09-04T10:00:00Z",
		fill_id: "fill-1",
		fill_price: 10,
		instrument_id: 510300,
		market_lineage_hash: "lineage-1",
		market_snapshot_hash: "snapshot-1",
		order_id: "different-order",
		quantity: 100,
		reference_price: 10,
		settlement_date: "2026-09-05",
		slippage: 0,
		tax: 0,
		total_cost: 5,
		trade_date: "2026-09-04",
		transfer_fee: 0,
	},
};

describe("manual account runtime boundary", () => {
	it("rejects an account-create response whose identity differs from the request", async () => {
		vi.stubGlobal(
			"fetch",
			respondWith({ account: { ...manualAccount, account_id: "manual-b" }, event: null, status: "created" }, 201),
		);

		await expect(
			createManualAccount({
				account_id: "manual-a",
				currency: "CNY",
				name: "Main",
				opened_at: "2026-09-04T00:00:00Z",
			}),
		).rejects.toThrow(/account_id/u);
	});

	it("rejects a structurally incomplete ledger success payload", async () => {
		vi.stubGlobal("fetch", respondWith({ account: manualAccount, events: [], snapshot: { account_kind: "manual" } }));

		await expect(fetchManualAccountLedger("manual-a", "2026-09-04")).rejects.toThrow(/snapshot/u);
	});

	it.each([
		["record", () => recordManualAccountEvent("manual-a", manualEventBody)],
		[
			"correct",
			() =>
				correctManualAccountEvent("manual-a", {
					corrects_event_id: "event-0",
					replacement: manualEventBody,
				}),
		],
		["reverse", () => reverseManualAccountEvent("manual-a", reverseManualEventBody)],
	])("rejects an incomplete %s event receipt", async (_name, invoke) => {
		vi.stubGlobal(
			"fetch",
			respondWith({ account: manualAccount, event: incompleteManualEvent, status: "created" }, 201),
		);

		await expect(invoke()).rejects.toThrow();
	});

	it("rejects correction and reversal receipts with a business-event discriminator", async () => {
		vi.stubGlobal("fetch", respondWith({ account: manualAccount, event: manualResponseEvent, status: "created" }, 201));
		await expect(
			correctManualAccountEvent("manual-a", { corrects_event_id: "event-0", replacement: manualEventBody }),
		).rejects.toThrow(/event_type/u);

		vi.stubGlobal(
			"fetch",
			respondWith(
				{
					account: manualAccount,
					event: { ...manualResponseEvent, idempotency_key: reverseManualEventBody.idempotency_key },
					status: "created",
				},
				201,
			),
		);
		await expect(reverseManualAccountEvent("manual-a", reverseManualEventBody)).rejects.toThrow(/event_type/u);
	});
});

describe("paper account runtime boundary", () => {
	it("rejects an account-create response with the wrong discriminator", async () => {
		vi.stubGlobal(
			"fetch",
			respondWith(
				{
					account_id: "paper-a",
					account_kind: "manual",
					name: "Paper",
					opening_event_id: null,
					status: "created",
				},
				201,
			),
		);

		await expect(createPaperAccount(paperAccountBody)).rejects.toThrow(/account_kind/u);
	});

	it("rejects a ledger whose snapshot identity does not match its account", async () => {
		vi.stubGlobal(
			"fetch",
			respondWith({
				account: {
					account_id: "paper-a",
					account_kind: "paper",
					currency: "CNY",
					name: "Paper",
					opened_at: "2026-09-04T00:00:00Z",
				},
				events: [],
				snapshot: { account_id: "paper-b", account_kind: "paper", currency: "CNY" },
			}),
		);

		await expect(fetchPaperAccountLedger("paper-a", "2026-09-04")).rejects.toThrow(/snapshot/u);
	});

	it.each([true, false])("rejects another session for start_immediately=%s", async (startImmediately) => {
		vi.stubGlobal(
			"fetch",
			respondWith(
				{
					action: startImmediately ? "start" : "create",
					status: "created",
					session: { session_id: "paper-s-other", status: "running" },
				},
				201,
			),
		);

		await expect(createPaperSession({ ...paperSessionBody, start_immediately: startImmediately })).rejects.toThrow(
			/session_id/u,
		);
	});

	it("rejects a session read containing a malformed execution", async () => {
		vi.stubGlobal(
			"fetch",
			respondWith({
				session: {
					account_id: "paper-a",
					created_at: "2026-09-04T09:00:00Z",
					pause_reason: null,
					revision: 1,
					session_id: "paper-s-1",
					status: "running",
					strategy_id: "strategy-1",
					trade_date: "2026-09-04",
					updated_at: "2026-09-04T09:01:00Z",
				},
				executions: [{ execution_id: "execution-1" }],
				latest_reconciliation: null,
			}),
		);

		await expect(fetchPaperSession("paper-s-1")).rejects.toThrow(/execution/u);
	});

	it("rejects an order fill linked to a different order", async () => {
		vi.stubGlobal("fetch", respondWith(paperExecution, 201));

		await expect(operatePaperOrder("paper-s-1", paperOrderBody)).rejects.toThrow(/order_id/u);
	});

	it("rejects a pause response with the wrong action", async () => {
		vi.stubGlobal(
			"fetch",
			respondWith({ action: "start", status: "created", session: { session_id: "paper-s-1", status: "paused" } }),
		);

		await expect(
			pausePaperSession("paper-s-1", { idempotency_key: "pause-1", reason: "operator pause" }),
		).rejects.toThrow(/action/u);
	});

	it("rejects reconciliation for another session", async () => {
		vi.stubGlobal(
			"fetch",
			respondWith({
				balanced: true,
				checksum: "checksum-1",
				fill_count: 1,
				ledger_fill_count: 1,
				order_count: 1,
				reconciled_at: "2026-09-04T16:00:00Z",
				reconciliation_id: "reconciliation-1",
				session_id: "paper-s-other",
				trade_date: "2026-09-04",
			}),
		);

		await expect(reconcilePaperSession("paper-s-1", { idempotency_key: "reconcile-1" })).rejects.toThrow(/session_id/u);
	});

	it("rejects a recovery response with a different idempotency identity", async () => {
		vi.stubGlobal("fetch", respondWith({ idempotency_key: "recover-other", recovered_execution_count: 1 }));

		await expect(recoverPaperSession("paper-s-1", { idempotency_key: "recover-1" })).rejects.toThrow(
			/idempotency_key/u,
		);
	});
});
