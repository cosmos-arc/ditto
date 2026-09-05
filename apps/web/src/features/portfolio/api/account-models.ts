export type ManualBusinessEventType =
	| "opening_cash"
	| "opening_position"
	| "buy"
	| "sell"
	| "deposit"
	| "withdrawal"
	| "fee"
	| "tax"
	| "interest"
	| "dividend"
	| "transfer_in"
	| "transfer_out"
	| "split"
	| "merge"
	| "other_corporate_action";

export type ManualAccountEventType = ManualBusinessEventType | "reversal" | "correction";

export interface CreateManualAccountBody {
	account_id: string;
	currency: "CNY";
	name: string;
	opened_at: string;
}

export interface ManualEventBody {
	actor: string;
	attachment_refs: string[];
	event_type: ManualBusinessEventType;
	external_reference?: string | null;
	fees: number | string;
	gross_amount: number | string;
	idempotency_key: string;
	instrument_id?: number | null;
	net_cash?: number | string | null;
	note: string;
	price: number | string;
	quantity: number | string;
	settlement_date: string;
	tax: number | string;
	trade_date: string;
}

export interface CorrectManualEventBody {
	corrects_event_id: string;
	replacement: ManualEventBody;
}

export interface ReverseManualEventBody {
	actor: string;
	idempotency_key: string;
	note: string;
	reverses_event_id: string;
	settlement_date: string;
	trade_date: string;
}

export interface ManualAccount {
	readonly account_id: string;
	readonly currency: "CNY";
	readonly kind: "manual";
	readonly name: string;
	readonly opened_at: string;
}

export interface ManualAccountEvent {
	readonly account_id: string;
	readonly account_kind: "manual";
	readonly actor: string;
	readonly attachment_refs: readonly string[];
	readonly corrects_event_id: string | null;
	readonly currency: "CNY";
	readonly event_hash: string;
	readonly event_id: string;
	readonly event_type: ManualAccountEventType;
	readonly external_reference: string | null;
	readonly fees: string;
	readonly gross_amount: string;
	readonly idempotency_key: string;
	readonly instrument_id: number | null;
	readonly net_cash: string;
	readonly note: string;
	readonly price: string;
	readonly quantity: string;
	readonly recorded_at: string;
	readonly replacement_event_type: ManualBusinessEventType | null;
	readonly reverses_event_id: string | null;
	readonly settlement_date: string;
	readonly source: "manual_entry" | "file_import";
	readonly tax: string;
	readonly trade_date: string;
}

export interface AccountCashSnapshot {
	readonly available: string;
	readonly frozen: string;
	readonly settled: string;
	readonly total: string;
}

export interface AccountPositionSnapshot {
	readonly available_quantity: string;
	readonly average_cost: string;
	readonly instrument_id: number;
	readonly last_price: string;
	readonly market_value: string;
	readonly quantity: string;
	readonly realized_pnl: string;
	readonly total_fees: string;
	readonly unrealized_pnl: string;
}

export interface ManualPortfolioSnapshot {
	readonly account_id: string;
	readonly account_kind: "manual";
	readonly as_of: string;
	readonly cash: AccountCashSnapshot;
	readonly currency: "CNY";
	readonly event_count: number;
	readonly ledger_hash: string;
	readonly positions: readonly AccountPositionSnapshot[];
	readonly realized_pnl: string;
	readonly total_fees: string;
	readonly total_value: string;
	readonly unrealized_pnl: string;
	readonly valuation_complete: boolean;
}

export interface ManualAccountLedger {
	readonly account: ManualAccount;
	readonly events: readonly ManualAccountEvent[];
	readonly snapshot: ManualPortfolioSnapshot;
}

export interface ManualAccountReceipt {
	readonly account: ManualAccount;
	readonly event: ManualAccountEvent | null;
	readonly status: "created" | "replayed";
}

export interface CreatePaperAccountBody {
	account_id: string;
	currency: "CNY";
	idempotency_key: string;
	initial_cash: number | string;
	name: string;
	opened_at: string;
	trade_date: string;
}

export interface CreatePaperSessionBody {
	account_id: string;
	idempotency_key: string;
	session_id: string;
	start_immediately: boolean;
	strategy_id: string;
	trade_date: string;
}

export interface PaperFillAssumptionBody {
	assumption_id: string;
	reference_price_field: "open" | "close";
	slippage_bps: number;
	version: number;
}

export interface PaperMarketSnapshotBody {
	amount: number;
	avg_volume_20d?: number | null;
	close: number;
	dataset_id: string;
	high: number;
	is_suspended: boolean;
	limit_down?: number | null;
	limit_up?: number | null;
	low: number;
	observed_at: string;
	open: number;
	prev_close: number;
	publication_cutoff: string;
	source: string;
	source_snapshot_id: string;
	volume: number;
}

export interface PaperInstrumentRulesBody {
	asset_class: string;
	board_segment: string;
	commission_rate: number;
	currency: "CNY";
	exchange: string;
	lifecycle_state: string;
	lot_size: number;
	min_commission: number;
	multiplier: number;
	price_limit_pct: number | null;
	settlement_cycle: number;
	stamp_duty_rate: number;
	tick_size: number;
	transfer_fee_rate: number;
}

export interface OperatePaperOrderBody {
	assumption: PaperFillAssumptionBody;
	available_quantity: number;
	decision_at: string;
	execution_at: string;
	idempotency_key: string;
	instrument_id: number;
	market: PaperMarketSnapshotBody;
	order_id: string;
	order_type: "market" | "limit";
	position_quantity: number;
	price?: number | null;
	quantity: number;
	rules: PaperInstrumentRulesBody;
	settlement_date: string;
	side: "buy" | "sell";
	trade_date: string;
}

export interface PausePaperSessionBody {
	idempotency_key: string;
	reason: string;
}

export interface ReconcilePaperSessionBody {
	idempotency_key: string;
}

export interface RecoverPaperSessionBody {
	idempotency_key: string;
}

export interface PaperAccountIdentity {
	readonly account_id: string;
	readonly account_kind: "paper";
	readonly currency: "CNY";
	readonly name: string;
	readonly opened_at: string;
}

export interface PaperAccountReceipt {
	readonly account_id: string;
	readonly account_kind: "paper";
	readonly name: string;
	readonly opening_event_id: string | null;
	readonly status: "created" | "replayed";
}

export interface PaperLedgerEvent {
	readonly account_id: string;
	readonly account_kind: "paper";
	readonly actor: string;
	readonly currency: "CNY";
	readonly event_hash: string;
	readonly event_id: string;
	readonly event_type: string;
	readonly external_reference: string | null;
	readonly fees: string;
	readonly gross_amount: string;
	readonly idempotency_key: string;
	readonly instrument_id: number | null;
	readonly net_cash: string;
	readonly note: string;
	readonly price: string;
	readonly quantity: string;
	readonly recorded_at: string;
	readonly settlement_date: string;
	readonly source: "paper_engine";
	readonly tax: string;
	readonly trade_date: string;
}

export interface PaperPortfolioSnapshot {
	readonly account_id: string;
	readonly account_kind: "paper";
	readonly as_of: string;
	readonly cash: AccountCashSnapshot;
	readonly currency: "CNY";
	readonly event_count: number;
	readonly ledger_hash: string;
	readonly positions: readonly AccountPositionSnapshot[];
	readonly realized_pnl: string;
	readonly total_fees: string;
	readonly total_value: string;
	readonly unrealized_pnl: string;
	readonly valuation_complete: boolean;
}

export interface PaperAccountLedger {
	readonly account: PaperAccountIdentity;
	readonly events: readonly PaperLedgerEvent[];
	readonly snapshot: PaperPortfolioSnapshot;
}

export interface PaperSession {
	readonly account_id: string;
	readonly created_at: string;
	readonly pause_reason: string | null;
	readonly revision: number;
	readonly session_id: string;
	readonly status: "created" | "running" | "paused";
	readonly strategy_id: string;
	readonly trade_date: string;
	readonly updated_at: string;
}

export interface PaperFill {
	readonly assumption_hash: string;
	readonly commission: number;
	readonly direction: "buy" | "sell";
	readonly event_time: string;
	readonly fill_id: string;
	readonly fill_price: number;
	readonly instrument_id: number;
	readonly market_lineage_hash: string;
	readonly market_snapshot_hash: string;
	readonly order_id: string;
	readonly quantity: number;
	readonly reference_price: number;
	readonly settlement_date: string;
	readonly slippage: number;
	readonly tax: number;
	readonly total_cost: number;
	readonly trade_date: string;
	readonly transfer_fee: number;
}

export type PaperOrderStatus =
	| "new"
	| "submitted"
	| "partially_filled"
	| "filled"
	| "canceled"
	| "rejected"
	| "invalid";

export type PaperRealityStatus = "filled" | "deferred" | "rejected";

export interface PaperExecutionReceipt {
	readonly execution_id: string;
	readonly fill: PaperFill | null;
	readonly idempotency_key: string;
	readonly ledger_event_id: string | null;
	readonly order_id: string;
	readonly order_status: PaperOrderStatus;
	readonly reality_status: PaperRealityStatus;
	readonly reason: string | null;
	readonly request_hash: string;
	readonly status: "created" | "replayed";
}

export interface PaperReconciliation {
	readonly balanced: boolean;
	readonly checksum: string;
	readonly fill_count: number;
	readonly ledger_fill_count: number;
	readonly order_count: number;
	readonly reconciled_at: string;
	readonly reconciliation_id: string;
	readonly session_id: string;
	readonly trade_date: string;
}

export interface PaperRecoverReceipt {
	readonly idempotency_key: string;
	readonly recovered_execution_count: number;
}

export interface PaperSessionCommandReceipt {
	readonly action: "create" | "start" | "pause";
	readonly session: PaperSession;
	readonly status: "created" | "replayed";
}

export interface PaperSessionRead {
	readonly executions: readonly PaperExecutionReceipt[];
	readonly latest_reconciliation: PaperReconciliation | null;
	readonly session: PaperSession;
}
