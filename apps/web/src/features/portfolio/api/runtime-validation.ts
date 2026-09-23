import type { components } from "@/api/generated/schema";
import {
	arrayValue,
	booleanValue,
	enumValue,
	integerValue,
	RuntimeValidationError,
	recordValue,
	stringValue,
} from "@/api/validation";
import type {
	AccountCashSnapshot,
	AccountCatalogEntry,
	AccountPositionSnapshot,
	HistoryComparison,
	HistoryComparisonLeg,
	HistoryComparisonRun,
	HistoryComparisonRunPoint,
	ManualAccount,
	ManualAccountEvent,
	ManualAccountHistory,
	ManualAccountLedger,
	ManualAccountReceipt,
	ManualBusinessEventType,
	ManualHistoryPoint,
	ManualHistoryQuality,
	ManualHistoryQueryIdentity,
	ManualLedgerRevision,
	ModelHistory,
	PaperAccountHistory,
	PaperAccountIdentity,
	PaperAccountLedger,
	PaperAccountReceipt,
	PaperExecutionReceipt,
	PaperFill,
	PaperLedgerEvent,
	PaperPortfolioSnapshot,
	PaperReconciliation,
	PaperRecoverReceipt,
	PaperSession,
	PaperSessionCatalogEntry,
	PaperSessionCommandReceipt,
	PaperSessionRead,
} from "./account-models";

type FillAdjustment = components["schemas"]["FillAdjustmentResponse"];
type DailyDecisionV3 = components["schemas"]["DailyDecisionV3Response"];
type PortfolioScenarioPreview = components["schemas"]["PortfolioScenarioPreviewResponse"];

const MANUAL_BUSINESS_EVENT_TYPES = [
	"opening_cash",
	"opening_position",
	"buy",
	"sell",
	"deposit",
	"withdrawal",
	"fee",
	"tax",
	"interest",
	"dividend",
	"transfer_in",
	"transfer_out",
	"split",
	"merge",
	"other_corporate_action",
] as const satisfies readonly ManualBusinessEventType[];

const MANUAL_EVENT_TYPES = [...MANUAL_BUSINESS_EVENT_TYPES, "reversal", "correction"] as const;

const MANUAL_FLOW_POSITIONS = ["start_of_day", "end_of_day", "intraday"] as const;

type ManualReceiptExpectation =
	| { readonly accountId: string; readonly kind: "account" }
	| {
			readonly accountId: string;
			readonly eventType: ManualBusinessEventType;
			readonly idempotencyKey: string;
			readonly kind: "business";
	  }
	| {
			readonly accountId: string;
			readonly correctsEventId: string;
			readonly idempotencyKey: string;
			readonly kind: "correction";
			readonly replacementEventType: ManualBusinessEventType;
	  }
	| {
			readonly accountId: string;
			readonly idempotencyKey: string;
			readonly kind: "reversal";
			readonly reversesEventId: string;
	  };

function textValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string {
	const value = record[field];
	if (typeof value !== "string") throw new RuntimeValidationError(boundary, field, "expected a string");
	return value;
}

function decimalValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string {
	const value = stringValue(record, field, boundary);
	if (!Number.isFinite(Number(value))) {
		throw new RuntimeValidationError(boundary, field, "expected a finite decimal string");
	}
	return value;
}

function finiteNumberValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): number {
	const value = record[field];
	if (typeof value !== "number" || !Number.isFinite(value)) {
		throw new RuntimeValidationError(boundary, field, "expected a finite number");
	}
	return value;
}

function nullableStringValue(
	record: Readonly<Record<string, unknown>>,
	field: string,
	boundary: string,
): string | null {
	if (record[field] === null) return null;
	return stringValue(record, field, boundary);
}

function nullableTextValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string | null {
	if (record[field] === null) return null;
	return textValue(record, field, boundary);
}

function nullableIntegerValue(
	record: Readonly<Record<string, unknown>>,
	field: string,
	boundary: string,
): number | null {
	if (record[field] === null) return null;
	return integerValue(record, field, boundary, 1);
}

function sameValue(actual: unknown, expected: unknown, boundary: string, field: string): void {
	if (actual !== expected) {
		throw new RuntimeValidationError(boundary, field, `expected ${String(expected)}`);
	}
}

function parseStringArray(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string[] {
	return arrayValue(record, field, boundary).map((value, index) => {
		if (typeof value !== "string") {
			throw new RuntimeValidationError(`${boundary}.${field}`, String(index), "expected a string");
		}
		return value;
	});
}

function parseManualAccount(value: unknown, boundary: string): ManualAccount {
	const record = recordValue(value, boundary);
	return {
		account_id: stringValue(record, "account_id", boundary),
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		kind: enumValue(record, "kind", ["manual"] as const, boundary),
		name: stringValue(record, "name", boundary),
		opened_at: stringValue(record, "opened_at", boundary),
	};
}

function parseCashSnapshot(value: unknown, boundary: string): AccountCashSnapshot {
	const record = recordValue(value, boundary);
	return {
		available: decimalValue(record, "available", boundary),
		frozen: decimalValue(record, "frozen", boundary),
		settled: decimalValue(record, "settled", boundary),
		total: decimalValue(record, "total", boundary),
	};
}

function parsePositionSnapshot(value: unknown, boundary: string): AccountPositionSnapshot {
	const record = recordValue(value, boundary);
	return {
		available_quantity: decimalValue(record, "available_quantity", boundary),
		average_cost: decimalValue(record, "average_cost", boundary),
		instrument_id: integerValue(record, "instrument_id", boundary, 1),
		last_price: decimalValue(record, "last_price", boundary),
		market_value: decimalValue(record, "market_value", boundary),
		quantity: decimalValue(record, "quantity", boundary),
		realized_pnl: decimalValue(record, "realized_pnl", boundary),
		total_fees: decimalValue(record, "total_fees", boundary),
		unrealized_pnl: decimalValue(record, "unrealized_pnl", boundary),
	};
}

function parseManualEvent(value: unknown, accountId: string, boundary: string): ManualAccountEvent {
	const record = recordValue(value, boundary);
	const eventType = enumValue(record, "event_type", MANUAL_EVENT_TYPES, boundary);
	const correctsEventId = nullableStringValue(record, "corrects_event_id", boundary);
	const replacementEventType =
		record["replacement_event_type"] === null
			? null
			: enumValue(record, "replacement_event_type", MANUAL_BUSINESS_EVENT_TYPES, boundary);
	const reversesEventId = nullableStringValue(record, "reverses_event_id", boundary);
	sameValue(record["account_id"], accountId, boundary, "account_id");
	if (eventType === "correction") {
		if (correctsEventId === null || replacementEventType === null || reversesEventId !== null) {
			throw new RuntimeValidationError(boundary, "event_type", "correction linkage is incomplete");
		}
	} else if (eventType === "reversal") {
		if (reversesEventId === null || correctsEventId !== null || replacementEventType !== null) {
			throw new RuntimeValidationError(boundary, "event_type", "reversal linkage is incomplete");
		}
	} else if (correctsEventId !== null || replacementEventType !== null || reversesEventId !== null) {
		throw new RuntimeValidationError(boundary, "event_type", "business event cannot carry control linkage");
	}
	return {
		account_id: accountId,
		account_kind: enumValue(record, "account_kind", ["manual"] as const, boundary),
		actor: stringValue(record, "actor", boundary),
		attachment_refs: parseStringArray(record, "attachment_refs", boundary),
		corrects_event_id: correctsEventId,
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		event_hash: stringValue(record, "event_hash", boundary),
		event_id: stringValue(record, "event_id", boundary),
		event_type: eventType,
		external_reference: nullableTextValue(record, "external_reference", boundary),
		fees: decimalValue(record, "fees", boundary),
		flow_position:
			record["flow_position"] === null || record["flow_position"] === undefined
				? null
				: enumValue(record, "flow_position", MANUAL_FLOW_POSITIONS, boundary),
		gross_amount: decimalValue(record, "gross_amount", boundary),
		idempotency_key: stringValue(record, "idempotency_key", boundary),
		instrument_id: nullableIntegerValue(record, "instrument_id", boundary),
		net_cash: decimalValue(record, "net_cash", boundary),
		note: textValue(record, "note", boundary),
		price: decimalValue(record, "price", boundary),
		quantity: decimalValue(record, "quantity", boundary),
		recorded_at: stringValue(record, "recorded_at", boundary),
		replacement_event_type: replacementEventType,
		reverses_event_id: reversesEventId,
		settlement_date: stringValue(record, "settlement_date", boundary),
		source: enumValue(record, "source", ["manual_entry", "file_import"] as const, boundary),
		tax: decimalValue(record, "tax", boundary),
		trade_date: stringValue(record, "trade_date", boundary),
	};
}

function parseManualSnapshot(
	value: unknown,
	expectedAccountId: string,
	expectedAsOf: string | undefined,
	boundary: string,
) {
	const record = recordValue(value, boundary);
	sameValue(record["account_id"], expectedAccountId, boundary, "account_id");
	if (expectedAsOf !== undefined) sameValue(record["as_of"], expectedAsOf, boundary, "as_of");
	return {
		account_id: expectedAccountId,
		account_kind: enumValue(record, "account_kind", ["manual"] as const, boundary),
		as_of: stringValue(record, "as_of", boundary),
		cash: parseCashSnapshot(record["cash"], `${boundary}.cash`),
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		event_count: integerValue(record, "event_count", boundary, 0),
		ledger_hash: stringValue(record, "ledger_hash", boundary),
		positions: arrayValue(record, "positions", boundary).map((position, index) =>
			parsePositionSnapshot(position, `${boundary}.positions.${index}`),
		),
		realized_pnl: decimalValue(record, "realized_pnl", boundary),
		total_fees: decimalValue(record, "total_fees", boundary),
		total_value: decimalValue(record, "total_value", boundary),
		unrealized_pnl: decimalValue(record, "unrealized_pnl", boundary),
		valuation_complete: booleanValue(record, "valuation_complete", boundary),
	};
}

export function parseManualAccountReceipt(
	value: unknown,
	expectation?: ManualReceiptExpectation,
): ManualAccountReceipt {
	const boundary = "manualAccountReceipt";
	const record = recordValue(value, boundary);
	const account = parseManualAccount(record["account"], `${boundary}.account`);
	const event =
		record["event"] === null ? null : parseManualEvent(record["event"], account.account_id, `${boundary}.event`);
	const receipt: ManualAccountReceipt = {
		account,
		event,
		status: enumValue(record, "status", ["created", "replayed"] as const, boundary),
	};
	if (expectation === undefined) return receipt;
	sameValue(account.account_id, expectation.accountId, `${boundary}.account`, "account_id");
	if (expectation.kind === "account") {
		if (event !== null)
			throw new RuntimeValidationError(boundary, "event", "account creation must not append an event");
		return receipt;
	}
	if (event === null) throw new RuntimeValidationError(boundary, "event", "expected an appended event");
	sameValue(event.idempotency_key, expectation.idempotencyKey, `${boundary}.event`, "idempotency_key");
	if (expectation.kind === "business") {
		sameValue(event.event_type, expectation.eventType, `${boundary}.event`, "event_type");
	} else if (expectation.kind === "correction") {
		sameValue(event.event_type, "correction", `${boundary}.event`, "event_type");
		sameValue(event.corrects_event_id, expectation.correctsEventId, `${boundary}.event`, "corrects_event_id");
		sameValue(
			event.replacement_event_type,
			expectation.replacementEventType,
			`${boundary}.event`,
			"replacement_event_type",
		);
	} else {
		sameValue(event.event_type, "reversal", `${boundary}.event`, "event_type");
		sameValue(event.reverses_event_id, expectation.reversesEventId, `${boundary}.event`, "reverses_event_id");
	}
	return receipt;
}

export function parseManualAccountLedger(
	value: unknown,
	expectedAccountId: string,
	expectedAsOf: string,
): ManualAccountLedger {
	const boundary = "manualAccountLedger";
	const record = recordValue(value, boundary);
	const account = parseManualAccount(record["account"], `${boundary}.account`);
	sameValue(account.account_id, expectedAccountId, `${boundary}.account`, "account_id");
	return {
		account,
		events: arrayValue(record, "events", boundary).map((event, index) =>
			parseManualEvent(event, expectedAccountId, `${boundary}.events.${index}`),
		),
		ledger_revision: parseLedgerRevision(record["ledger_revision"], `${boundary}.ledger_revision`),
		snapshot: parseManualSnapshot(record["snapshot"], expectedAccountId, expectedAsOf, `${boundary}.snapshot`),
	};
}

function parseLedgerRevision(value: unknown, boundary: string): ManualLedgerRevision {
	const record = recordValue(value, boundary);
	return {
		event_count: finiteNumberValue(record, "event_count", boundary),
		ledger_hash: stringValue(record, "ledger_hash", boundary),
	};
}

function sameInstant(actual: unknown, expected: string, boundary: string, field: string): void {
	if (typeof actual !== "string" || !Number.isFinite(Date.parse(actual))) {
		throw new RuntimeValidationError(boundary, field, "expected an RFC3339 timestamp");
	}
	if (Date.parse(actual) !== Date.parse(expected)) {
		throw new RuntimeValidationError(boundary, field, `${field} instant mismatch`);
	}
}

function parseHistoryQuality(value: unknown, boundary: string): ManualHistoryQuality {
	const record = recordValue(value, boundary);
	return {
		code: stringValue(record, "code", boundary),
		detail: typeof record["detail"] === "string" ? record["detail"] : "",
	};
}

function parseHistoryQualities(
	record: Readonly<Record<string, unknown>>,
	field: string,
	boundary: string,
): ManualHistoryQuality[] {
	return arrayValue(record, field, boundary).map((item, index) =>
		parseHistoryQuality(item, `${boundary}.${field}.${index}`),
	);
}

function nullableDecimal(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string | null {
	return record[field] === null ? null : decimalValue(record, field, boundary);
}

function parseHistoryPoint(value: unknown, boundary: string): ManualHistoryPoint {
	const record = recordValue(value, boundary);
	return {
		on_date: stringValue(record, "on_date", boundary),
		valuation_instant: stringValue(record, "valuation_instant", boundary),
		total_value: nullableDecimal(record, "total_value", boundary),
		cash: nullableDecimal(record, "cash", boundary),
		external_flow: decimalValue(record, "external_flow", boundary),
		period_return: nullableDecimal(record, "period_return", boundary),
		cumulative_return: nullableDecimal(record, "cumulative_return", boundary),
		segment_id: record["segment_id"] === null ? null : integerValue(record, "segment_id", boundary),
		price_time: nullableTextValue(record, "price_time", boundary),
		stale: booleanValue(record, "stale", boundary),
		source_snapshot_ids: parseStringArray(record, "source_snapshot_ids", boundary),
		quality: parseHistoryQualities(record, "quality", boundary),
	};
}

type HistoryParseScope = {
	readonly boundary: string;
	readonly resultIdPrefix: string;
};

export function parseManualAccountHistory(
	value: unknown,
	expectedAccountId: string,
	identity: ManualHistoryQueryIdentity,
): ManualAccountHistory {
	return parseAccountHistoryPayload(
		value,
		{ boundary: "manualAccountHistory", resultIdPrefix: "manual-history:sha256:" },
		expectedAccountId,
		identity,
	);
}

export function parsePaperAccountHistory(
	value: unknown,
	expectedAccountId: string,
	identity: ManualHistoryQueryIdentity,
): PaperAccountHistory {
	return parseAccountHistoryPayload(
		value,
		{ boundary: "paperAccountHistory", resultIdPrefix: "paper-history:sha256:" },
		expectedAccountId,
		identity,
	);
}

function parseAccountHistoryPayload(
	value: unknown,
	scope: HistoryParseScope,
	expectedAccountId: string,
	identity: ManualHistoryQueryIdentity,
): ManualAccountHistory {
	const { boundary, resultIdPrefix } = scope;
	const record = recordValue(value, boundary);
	sameValue(record["account_id"], expectedAccountId, boundary, "account_id");
	sameValue(record["start_date"], identity.start_date, boundary, "start_date");
	sameValue(record["end_date"], identity.end_date, boundary, "end_date");
	sameInstant(record["knowledge_cutoff"], identity.knowledge_cutoff, boundary, "knowledge_cutoff");
	sameInstant(record["publication_cutoff"], identity.publication_cutoff, boundary, "publication_cutoff");
	const resultId = stringValue(record, "result_id", boundary);
	if (!resultId.startsWith(resultIdPrefix)) {
		throw new RuntimeValidationError(boundary, "result_id", `must start with ${resultIdPrefix}`);
	}
	const ledgerRevision = parseLedgerRevision(record["ledger_revision"], `${boundary}.ledger_revision`);
	sameValue(ledgerRevision.ledger_hash, identity.ledger_hash, `${boundary}.ledger_revision`, "ledger_hash");
	return {
		result_id: resultId,
		account_id: expectedAccountId,
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		start_date: identity.start_date,
		end_date: identity.end_date,
		knowledge_cutoff: identity.knowledge_cutoff,
		publication_cutoff: identity.publication_cutoff,
		source_snapshot_ids: parseStringArray(record, "source_snapshot_ids", boundary),
		ledger_revision: ledgerRevision,
		method: stringValue(record, "method", boundary),
		valuation_policy_version: stringValue(record, "valuation_policy_version", boundary),
		points: arrayValue(record, "points", boundary).map((point, index) =>
			parseHistoryPoint(point, `${boundary}.points.${index}`),
		),
		segments: arrayValue(record, "segments", boundary).map((segment, index) => {
			const segmentBoundary = `${boundary}.segments.${index}`;
			const segmentRecord = recordValue(segment, segmentBoundary);
			return {
				segment_id: finiteNumberValue(segmentRecord, "segment_id", segmentBoundary),
				start_date: stringValue(segmentRecord, "start_date", segmentBoundary),
				end_date: stringValue(segmentRecord, "end_date", segmentBoundary),
				start_value: decimalValue(segmentRecord, "start_value", segmentBoundary),
				end_value: decimalValue(segmentRecord, "end_value", segmentBoundary),
				linked_return: nullableDecimal(segmentRecord, "linked_return", segmentBoundary),
				closed_reason: enumValue(
					segmentRecord,
					"closed_reason",
					["range_end", "loss_to_zero", "full_withdrawal", "valuation_gap", "negative_equity"] as const,
					segmentBoundary,
				),
				quality: parseHistoryQualities(segmentRecord, "quality", segmentBoundary),
			};
		}),
	};
}

export function assertManualAccountReceipt(value: unknown): asserts value is ManualAccountReceipt {
	parseManualAccountReceipt(value);
}

export function parseModelHistory(
	value: unknown,
	strategyId: string,
	identity: {
		readonly start_date: string;
		readonly end_date: string;
		readonly knowledge_cutoff: string;
		readonly publication_cutoff: string;
		readonly initial_capital: number | string;
	},
): ModelHistory {
	const boundary = "modelHistory";
	const record = recordValue(value, boundary);
	sameValue(record["strategy_id"], strategyId, boundary, "strategy_id");
	sameValue(record["start_date"], identity.start_date, boundary, "start_date");
	sameValue(record["end_date"], identity.end_date, boundary, "end_date");
	sameInstant(record["knowledge_cutoff"], identity.knowledge_cutoff, boundary, "knowledge_cutoff");
	sameInstant(record["publication_cutoff"], identity.publication_cutoff, boundary, "publication_cutoff");
	const initialCapital = decimalValue(record, "initial_capital", boundary);
	const requestedCapital = Number(identity.initial_capital);
	// Compare capital numerically: the server echoes a 2dp decimal string
	// while callers may submit "1e5" or ".5" shaped numbers.
	if (Number(initialCapital) !== requestedCapital) {
		throw new RuntimeValidationError(boundary, "initial_capital", "differs from the request");
	}
	const resultId = stringValue(record, "result_id", boundary);
	if (!resultId.startsWith("model-history:sha256:")) {
		throw new RuntimeValidationError(boundary, "result_id", "must start with model-history:sha256:");
	}
	const emptyReason = record["empty_reason"] === null ? null : stringValue(record, "empty_reason", boundary);
	return {
		result_id: resultId,
		strategy_id: strategyId,
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		start_date: identity.start_date,
		end_date: identity.end_date,
		initial_capital: initialCapital,
		knowledge_cutoff: identity.knowledge_cutoff,
		publication_cutoff: identity.publication_cutoff,
		empty_reason: emptyReason,
		targets: arrayValue(record, "targets", boundary).map((target, index) => {
			const targetBoundary = `${boundary}.targets.${index}`;
			const targetRecord = recordValue(target, targetBoundary);
			return {
				signal_date: stringValue(targetRecord, "signal_date", targetBoundary),
				artifact_id: stringValue(targetRecord, "artifact_id", targetBoundary),
				checksum: stringValue(targetRecord, "checksum", targetBoundary),
			};
		}),
		method: stringValue(record, "method", boundary),
		valuation_policy_version: stringValue(record, "valuation_policy_version", boundary),
		points: arrayValue(record, "points", boundary).map((point, index) =>
			parseHistoryPoint(point, `${boundary}.points.${index}`),
		),
		segments: arrayValue(record, "segments", boundary).map((segment, index) => {
			const segmentBoundary = `${boundary}.segments.${index}`;
			const segmentRecord = recordValue(segment, segmentBoundary);
			return {
				segment_id: finiteNumberValue(segmentRecord, "segment_id", segmentBoundary),
				start_date: stringValue(segmentRecord, "start_date", segmentBoundary),
				end_date: stringValue(segmentRecord, "end_date", segmentBoundary),
				start_value: decimalValue(segmentRecord, "start_value", segmentBoundary),
				end_value: decimalValue(segmentRecord, "end_value", segmentBoundary),
				linked_return: nullableDecimal(segmentRecord, "linked_return", segmentBoundary),
				closed_reason: enumValue(
					segmentRecord,
					"closed_reason",
					["range_end", "loss_to_zero", "full_withdrawal", "valuation_gap", "negative_equity"] as const,
					segmentBoundary,
				),
				quality: parseHistoryQualities(segmentRecord, "quality", segmentBoundary),
			};
		}),
	};
}

function parsePaperAccountIdentity(value: unknown, boundary: string): PaperAccountIdentity {
	const record = recordValue(value, boundary);
	return {
		account_id: stringValue(record, "account_id", boundary),
		account_kind: enumValue(record, "account_kind", ["paper"] as const, boundary),
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		name: stringValue(record, "name", boundary),
		opened_at: stringValue(record, "opened_at", boundary),
	};
}

const COMPARISON_LEG_KINDS = ["model", "paper", "manual"] as const;

function parseLegDecimalRecord(
	container: Readonly<Record<string, unknown>>,
	field: "growth" | "assets",
	boundary: string,
): Readonly<Record<(typeof COMPARISON_LEG_KINDS)[number], string>> {
	const record = recordValue(container[field], `${boundary}.${field}`);
	const result = {} as Record<(typeof COMPARISON_LEG_KINDS)[number], string>;
	for (const kind of COMPARISON_LEG_KINDS) {
		result[kind] = decimalValue(record, kind, `${boundary}.${field}`);
	}
	return result;
}

function parseLegReturnRecord(
	container: Readonly<Record<string, unknown>>,
	boundary: string,
): Readonly<Record<(typeof COMPARISON_LEG_KINDS)[number], string | null>> {
	const record = recordValue(container["window_returns"], `${boundary}.window_returns`);
	const result = {} as Record<(typeof COMPARISON_LEG_KINDS)[number], string | null>;
	for (const kind of COMPARISON_LEG_KINDS) {
		result[kind] = nullableDecimal(record, kind, `${boundary}.window_returns`);
	}
	return result;
}

/**
 * A pinned ledger revision must come back as that leg's resolved revision:
 * the server replays the pinned append-order prefix, so any other echo means
 * the pin was not honored.
 */
function assertPinnedRevision(
	legs: readonly HistoryComparisonLeg[],
	kind: "paper" | "manual",
	pin: {
		readonly event_count?: number | null | undefined;
		readonly ledger_hash?: string | null | undefined;
	},
	boundary: string,
): void {
	const { event_count: eventCount, ledger_hash: ledgerHash } = pin;
	if (eventCount === undefined || eventCount === null || ledgerHash === undefined || ledgerHash === null) {
		return;
	}
	const leg = legs.find((entry) => entry.kind === kind);
	const revision = leg?.ledger_revision ?? null;
	if (revision === null || revision.event_count !== eventCount || revision.ledger_hash !== ledgerHash) {
		throw new RuntimeValidationError(`${boundary}.legs.${kind}`, "ledger_revision", "differs from the pinned request");
	}
}

export function parseHistoryComparison(
	value: unknown,
	identity: {
		readonly strategy_id: string;
		readonly paper_account_id: string;
		readonly paper_session_id: string;
		readonly manual_account_id: string;
		readonly start_date: string;
		readonly end_date: string;
		readonly model_initial_capital: number | string;
		readonly knowledge_cutoff: string;
		readonly publication_cutoff: string;
		readonly paper_ledger_event_count?: number | null;
		readonly paper_ledger_hash?: string | null;
		readonly manual_ledger_event_count?: number | null;
		readonly manual_ledger_hash?: string | null;
	},
): HistoryComparison {
	const boundary = "historyComparison";
	const record = recordValue(value, boundary);
	sameValue(record["strategy_id"], identity.strategy_id, boundary, "strategy_id");
	sameValue(record["paper_account_id"], identity.paper_account_id, boundary, "paper_account_id");
	sameValue(record["paper_session_id"], identity.paper_session_id, boundary, "paper_session_id");
	sameValue(record["manual_account_id"], identity.manual_account_id, boundary, "manual_account_id");
	sameValue(record["start_date"], identity.start_date, boundary, "start_date");
	sameValue(record["end_date"], identity.end_date, boundary, "end_date");
	sameInstant(record["knowledge_cutoff"], identity.knowledge_cutoff, boundary, "knowledge_cutoff");
	sameInstant(record["publication_cutoff"], identity.publication_cutoff, boundary, "publication_cutoff");
	const capital = decimalValue(record, "model_initial_capital", boundary);
	if (Number(capital) !== Number(identity.model_initial_capital)) {
		throw new RuntimeValidationError(boundary, "model_initial_capital", "differs from the request");
	}
	const resultId = stringValue(record, "result_id", boundary);
	if (!resultId.startsWith("history-comparison:sha256:")) {
		throw new RuntimeValidationError(boundary, "result_id", "must start with history-comparison:sha256:");
	}
	const status = enumValue(record, "status", ["comparable", "single_common_point", "incomparable"] as const, boundary);
	const emptyReason = record["empty_reason"] === null ? null : stringValue(record, "empty_reason", boundary);
	const runs: HistoryComparisonRun[] = arrayValue(record, "runs", boundary).map((run, runIndex) => {
		const runBoundary = `${boundary}.runs.${runIndex}`;
		const runRecord = recordValue(run, runBoundary);
		const points: HistoryComparisonRunPoint[] = arrayValue(runRecord, "points", runBoundary).map(
			(point, pointIndex) => {
				const pointBoundary = `${runBoundary}.points.${pointIndex}`;
				const pointRecord = recordValue(point, pointBoundary);
				return {
					on_date: stringValue(pointRecord, "on_date", pointBoundary),
					growth: parseLegDecimalRecord(pointRecord, "growth", pointBoundary),
					assets: parseLegDecimalRecord(pointRecord, "assets", pointBoundary),
				};
			},
		);
		return {
			start_date: stringValue(runRecord, "start_date", runBoundary),
			end_date: stringValue(runRecord, "end_date", runBoundary),
			point_count: finiteNumberValue(runRecord, "point_count", runBoundary),
			points,
			window_returns: parseLegReturnRecord(runRecord, runBoundary),
		};
	});
	const legs: HistoryComparisonLeg[] = arrayValue(record, "legs", boundary).map((leg, legIndex) => {
		const legBoundary = `${boundary}.legs.${legIndex}`;
		const legRecord = recordValue(leg, legBoundary);
		const revision = legRecord["ledger_revision"];
		const ledgerRevision: ManualLedgerRevision | null =
			revision === null
				? null
				: {
						event_count: finiteNumberValue(
							recordValue(revision, `${legBoundary}.ledger_revision`),
							"event_count",
							`${legBoundary}.ledger_revision`,
						),
						ledger_hash: stringValue(
							recordValue(revision, `${legBoundary}.ledger_revision`),
							"ledger_hash",
							`${legBoundary}.ledger_revision`,
						),
					};
		return {
			kind: enumValue(legRecord, "kind", COMPARISON_LEG_KINDS, legBoundary),
			result_id: stringValue(legRecord, "result_id", legBoundary),
			currency: enumValue(legRecord, "currency", ["CNY"] as const, legBoundary),
			empty_reason: nullableStringValue(legRecord, "empty_reason", legBoundary),
			point_count: finiteNumberValue(legRecord, "point_count", legBoundary),
			valued_point_count: finiteNumberValue(legRecord, "valued_point_count", legBoundary),
			gap_count: finiteNumberValue(legRecord, "gap_count", legBoundary),
			segment_count: finiteNumberValue(legRecord, "segment_count", legBoundary),
			first_valued_date: nullableStringValue(legRecord, "first_valued_date", legBoundary),
			last_valued_date: nullableStringValue(legRecord, "last_valued_date", legBoundary),
			ledger_revision: ledgerRevision,
			target_count: nullableIntegerValue(legRecord, "target_count", legBoundary),
		};
	});
	assertPinnedRevision(
		legs,
		"paper",
		{ event_count: identity.paper_ledger_event_count, ledger_hash: identity.paper_ledger_hash },
		boundary,
	);
	assertPinnedRevision(
		legs,
		"manual",
		{ event_count: identity.manual_ledger_event_count, ledger_hash: identity.manual_ledger_hash },
		boundary,
	);
	return {
		result_id: resultId,
		strategy_id: identity.strategy_id,
		paper_account_id: identity.paper_account_id,
		paper_session_id: identity.paper_session_id,
		manual_account_id: identity.manual_account_id,
		model_initial_capital: capital,
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		method: stringValue(record, "method", boundary),
		valuation_policy_version: stringValue(record, "valuation_policy_version", boundary),
		comparison_policy_version: stringValue(record, "comparison_policy_version", boundary),
		status,
		empty_reason: emptyReason,
		start_date: identity.start_date,
		end_date: identity.end_date,
		knowledge_cutoff: identity.knowledge_cutoff,
		publication_cutoff: identity.publication_cutoff,
		runs,
		legs,
	};
}

function parseAccountEntry(value: unknown, kind: "manual" | "paper", boundary: string): AccountCatalogEntry {
	const record = recordValue(value, boundary);
	return {
		account_id: stringValue(record, "account_id", boundary),
		account_kind: sameKind(record["account_kind"], kind, boundary),
		account_name: stringValue(record, "account_name", boundary),
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		opened_at: stringValue(record, "opened_at", boundary),
	};
}

function sameKind(actual: unknown, expected: "manual" | "paper", boundary: string): "manual" | "paper" {
	if (actual !== expected) {
		throw new RuntimeValidationError(boundary, "account_kind", `expected ${expected}`);
	}
	return expected;
}

export function parseAccountCatalog(value: unknown, kind: "manual" | "paper"): readonly AccountCatalogEntry[] {
	const boundary = `${kind}AccountCatalog`;
	const record = recordValue(value, boundary);
	return arrayValue(record, "accounts", boundary).map((entry, index) =>
		parseAccountEntry(entry, kind, `${boundary}.accounts.${index}`),
	);
}

export function parsePaperSessionCatalog(value: unknown, accountId: string): readonly PaperSessionCatalogEntry[] {
	const boundary = "paperSessionCatalog";
	const record = recordValue(value, boundary);
	return arrayValue(record, "sessions", boundary).map((entry, index) => {
		const entryBoundary = `${boundary}.sessions.${index}`;
		const entryRecord = recordValue(entry, entryBoundary);
		sameValue(entryRecord["account_id"], accountId, entryBoundary, "account_id");
		return {
			session_id: stringValue(entryRecord, "session_id", entryBoundary),
			account_id: accountId,
			strategy_id: stringValue(entryRecord, "strategy_id", entryBoundary),
			trade_date: stringValue(entryRecord, "trade_date", entryBoundary),
			status: enumValue(entryRecord, "status", ["created", "running", "paused"] as const, entryBoundary),
			revision: finiteNumberValue(entryRecord, "revision", entryBoundary),
			created_at: stringValue(entryRecord, "created_at", entryBoundary),
			updated_at: stringValue(entryRecord, "updated_at", entryBoundary),
		};
	});
}

function parsePaperLedgerEvent(value: unknown, accountId: string, boundary: string): PaperLedgerEvent {
	const record = recordValue(value, boundary);
	sameValue(record["account_id"], accountId, boundary, "account_id");
	return {
		account_id: accountId,
		account_kind: enumValue(record, "account_kind", ["paper"] as const, boundary),
		actor: stringValue(record, "actor", boundary),
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		event_hash: stringValue(record, "event_hash", boundary),
		event_id: stringValue(record, "event_id", boundary),
		event_type: stringValue(record, "event_type", boundary),
		external_reference: nullableTextValue(record, "external_reference", boundary),
		fees: decimalValue(record, "fees", boundary),
		gross_amount: decimalValue(record, "gross_amount", boundary),
		idempotency_key: stringValue(record, "idempotency_key", boundary),
		instrument_id: nullableIntegerValue(record, "instrument_id", boundary),
		net_cash: decimalValue(record, "net_cash", boundary),
		note: textValue(record, "note", boundary),
		price: decimalValue(record, "price", boundary),
		quantity: decimalValue(record, "quantity", boundary),
		recorded_at: stringValue(record, "recorded_at", boundary),
		settlement_date: stringValue(record, "settlement_date", boundary),
		source: enumValue(record, "source", ["paper_engine"] as const, boundary),
		tax: decimalValue(record, "tax", boundary),
		trade_date: stringValue(record, "trade_date", boundary),
	};
}

function parsePaperSnapshot(
	value: unknown,
	expectedAccountId: string,
	expectedAsOf: string,
	boundary: string,
): PaperPortfolioSnapshot {
	const record = recordValue(value, boundary);
	sameValue(record["account_id"], expectedAccountId, boundary, "account_id");
	sameValue(record["as_of"], expectedAsOf, boundary, "as_of");
	return {
		account_id: expectedAccountId,
		account_kind: enumValue(record, "account_kind", ["paper"] as const, boundary),
		as_of: expectedAsOf,
		cash: parseCashSnapshot(record["cash"], `${boundary}.cash`),
		currency: enumValue(record, "currency", ["CNY"] as const, boundary),
		event_count: integerValue(record, "event_count", boundary, 0),
		ledger_hash: stringValue(record, "ledger_hash", boundary),
		positions: arrayValue(record, "positions", boundary).map((position, index) =>
			parsePositionSnapshot(position, `${boundary}.positions.${index}`),
		),
		realized_pnl: decimalValue(record, "realized_pnl", boundary),
		total_fees: decimalValue(record, "total_fees", boundary),
		total_value: decimalValue(record, "total_value", boundary),
		unrealized_pnl: decimalValue(record, "unrealized_pnl", boundary),
		valuation_complete: booleanValue(record, "valuation_complete", boundary),
	};
}

export function parsePaperAccountReceipt(value: unknown, expectedAccountId: string): PaperAccountReceipt {
	const boundary = "paperAccountReceipt";
	const record = recordValue(value, boundary);
	sameValue(record["account_id"], expectedAccountId, boundary, "account_id");
	return {
		account_id: expectedAccountId,
		account_kind: enumValue(record, "account_kind", ["paper"] as const, boundary),
		name: stringValue(record, "name", boundary),
		opening_event_id: nullableStringValue(record, "opening_event_id", boundary),
		status: enumValue(record, "status", ["created", "replayed"] as const, boundary),
	};
}

export function parsePaperAccountLedger(
	value: unknown,
	expectedAccountId: string,
	expectedAsOf: string,
): PaperAccountLedger {
	const boundary = "paperAccountLedger";
	const record = recordValue(value, boundary);
	const account = parsePaperAccountIdentity(record["account"], `${boundary}.account`);
	sameValue(account.account_id, expectedAccountId, `${boundary}.account`, "account_id");
	return {
		account,
		events: arrayValue(record, "events", boundary).map((event, index) =>
			parsePaperLedgerEvent(event, expectedAccountId, `${boundary}.events.${index}`),
		),
		snapshot: parsePaperSnapshot(record["snapshot"], expectedAccountId, expectedAsOf, `${boundary}.snapshot`),
	};
}

function parsePaperSession(value: unknown, expectedSessionId: string, boundary: string): PaperSession {
	const record = recordValue(value, boundary);
	sameValue(record["session_id"], expectedSessionId, boundary, "session_id");
	return {
		account_id: stringValue(record, "account_id", boundary),
		created_at: stringValue(record, "created_at", boundary),
		pause_reason: nullableTextValue(record, "pause_reason", boundary),
		revision: integerValue(record, "revision", boundary, 0),
		session_id: expectedSessionId,
		status: enumValue(record, "status", ["created", "running", "paused"] as const, boundary),
		strategy_id: stringValue(record, "strategy_id", boundary),
		trade_date: stringValue(record, "trade_date", boundary),
		updated_at: stringValue(record, "updated_at", boundary),
	};
}

function parsePaperFill(value: unknown, expectedOrderId: string, boundary: string): PaperFill {
	const record = recordValue(value, boundary);
	sameValue(record["order_id"], expectedOrderId, boundary, "order_id");
	return {
		assumption_hash: stringValue(record, "assumption_hash", boundary),
		commission: finiteNumberValue(record, "commission", boundary),
		direction: enumValue(record, "direction", ["buy", "sell"] as const, boundary),
		event_time: stringValue(record, "event_time", boundary),
		fill_id: stringValue(record, "fill_id", boundary),
		fill_price: finiteNumberValue(record, "fill_price", boundary),
		instrument_id: integerValue(record, "instrument_id", boundary, 1),
		market_lineage_hash: stringValue(record, "market_lineage_hash", boundary),
		market_snapshot_hash: stringValue(record, "market_snapshot_hash", boundary),
		order_id: expectedOrderId,
		quantity: integerValue(record, "quantity", boundary, 1),
		reference_price: finiteNumberValue(record, "reference_price", boundary),
		settlement_date: stringValue(record, "settlement_date", boundary),
		slippage: finiteNumberValue(record, "slippage", boundary),
		tax: finiteNumberValue(record, "tax", boundary),
		total_cost: finiteNumberValue(record, "total_cost", boundary),
		trade_date: stringValue(record, "trade_date", boundary),
		transfer_fee: finiteNumberValue(record, "transfer_fee", boundary),
	};
}

export function parsePaperExecutionReceipt(
	value: unknown,
	expected?: {
		readonly direction?: "buy" | "sell";
		readonly idempotencyKey?: string;
		readonly instrumentId?: number;
		readonly orderId?: string;
		readonly settlementDate?: string;
		readonly tradeDate?: string;
	},
): PaperExecutionReceipt {
	return parsePaperExecutionReceiptAt(value, expected, "paperExecutionReceipt");
}

function parsePaperExecutionReceiptAt(
	value: unknown,
	expected:
		| {
				readonly direction?: "buy" | "sell";
				readonly idempotencyKey?: string;
				readonly instrumentId?: number;
				readonly orderId?: string;
				readonly settlementDate?: string;
				readonly tradeDate?: string;
		  }
		| undefined,
	boundary: string,
): PaperExecutionReceipt {
	const record = recordValue(value, boundary);
	const orderId = stringValue(record, "order_id", boundary);
	if (expected?.orderId !== undefined) sameValue(orderId, expected.orderId, boundary, "order_id");
	const idempotencyKey = stringValue(record, "idempotency_key", boundary);
	if (expected?.idempotencyKey !== undefined) {
		sameValue(idempotencyKey, expected.idempotencyKey, boundary, "idempotency_key");
	}
	const fill = record["fill"] === null ? null : parsePaperFill(record["fill"], orderId, `${boundary}.fill`);
	if (fill !== null && expected !== undefined) {
		if (expected.direction !== undefined)
			sameValue(fill.direction, expected.direction, `${boundary}.fill`, "direction");
		if (expected.instrumentId !== undefined) {
			sameValue(fill.instrument_id, expected.instrumentId, `${boundary}.fill`, "instrument_id");
		}
		if (expected.settlementDate !== undefined) {
			sameValue(fill.settlement_date, expected.settlementDate, `${boundary}.fill`, "settlement_date");
		}
		if (expected.tradeDate !== undefined)
			sameValue(fill.trade_date, expected.tradeDate, `${boundary}.fill`, "trade_date");
	}
	const ledgerEventId = nullableStringValue(record, "ledger_event_id", boundary);
	if ((fill === null) !== (ledgerEventId === null)) {
		throw new RuntimeValidationError(boundary, "ledger_event_id", "fill and ledger event identities must agree");
	}
	return {
		execution_id: stringValue(record, "execution_id", boundary),
		fill,
		idempotency_key: idempotencyKey,
		ledger_event_id: ledgerEventId,
		order_id: orderId,
		order_status: enumValue(
			record,
			"order_status",
			["new", "submitted", "partially_filled", "filled", "canceled", "rejected", "invalid"] as const,
			boundary,
		),
		reality_status: enumValue(record, "reality_status", ["filled", "deferred", "rejected"] as const, boundary),
		reason: nullableTextValue(record, "reason", boundary),
		request_hash: stringValue(record, "request_hash", boundary),
		status: enumValue(record, "status", ["created", "replayed"] as const, boundary),
	};
}

export function assertPaperExecutionReceipt(value: unknown): asserts value is PaperExecutionReceipt {
	parsePaperExecutionReceipt(value);
}

export function parsePaperReconciliation(
	value: unknown,
	expectedSessionId: string,
	boundary = "paperReconciliation",
): PaperReconciliation {
	const record = recordValue(value, boundary);
	sameValue(record["session_id"], expectedSessionId, boundary, "session_id");
	return {
		balanced: booleanValue(record, "balanced", boundary),
		checksum: stringValue(record, "checksum", boundary),
		fill_count: integerValue(record, "fill_count", boundary, 0),
		ledger_fill_count: integerValue(record, "ledger_fill_count", boundary, 0),
		order_count: integerValue(record, "order_count", boundary, 0),
		reconciled_at: stringValue(record, "reconciled_at", boundary),
		reconciliation_id: stringValue(record, "reconciliation_id", boundary),
		session_id: expectedSessionId,
		trade_date: stringValue(record, "trade_date", boundary),
	};
}

export function parsePaperSessionCommandReceipt(
	value: unknown,
	expectedSessionId: string,
	expectedAction: "create" | "start" | "pause",
): PaperSessionCommandReceipt {
	const boundary = "paperSessionCommandReceipt";
	const record = recordValue(value, boundary);
	const action = enumValue(record, "action", ["create", "start", "pause"] as const, boundary);
	sameValue(action, expectedAction, boundary, "action");
	const session = parsePaperSession(record["session"], expectedSessionId, `${boundary}.session`);
	const expectedState = action === "create" ? "created" : action === "start" ? "running" : "paused";
	sameValue(session.status, expectedState, `${boundary}.session`, "status");
	return {
		action,
		session,
		status: enumValue(record, "status", ["created", "replayed"] as const, boundary),
	};
}

export function parsePaperSessionRead(value: unknown, expectedSessionId: string): PaperSessionRead {
	const boundary = "paperSessionRead";
	const record = recordValue(value, boundary);
	const session = parsePaperSession(record["session"], expectedSessionId, `${boundary}.session`);
	const latestReconciliation =
		record["latest_reconciliation"] === null
			? null
			: parsePaperReconciliation(
					record["latest_reconciliation"],
					expectedSessionId,
					`${boundary}.latest_reconciliation`,
				);
	if (latestReconciliation !== null) {
		sameValue(latestReconciliation.trade_date, session.trade_date, `${boundary}.latest_reconciliation`, "trade_date");
	}
	return {
		executions: arrayValue(record, "executions", boundary).map((execution, index) =>
			parsePaperExecutionReceiptAt(execution, undefined, `${boundary}.executions.${index}`),
		),
		latest_reconciliation: latestReconciliation,
		session,
	};
}

export function parsePaperRecoverReceipt(value: unknown, expectedIdempotencyKey: string): PaperRecoverReceipt {
	const boundary = "paperRecoverReceipt";
	const record = recordValue(value, boundary);
	sameValue(record["idempotency_key"], expectedIdempotencyKey, boundary, "idempotency_key");
	return {
		idempotency_key: expectedIdempotencyKey,
		recovered_execution_count: integerValue(record, "recovered_execution_count", boundary, 0),
	};
}

export function assertFillAdjustment(value: unknown): asserts value is FillAdjustment {
	const boundary = "fillAdjustment";
	const record = recordValue(value, boundary);
	stringValue(record, "adjustment_id", boundary);
	stringValue(record, "fill_id", boundary);
	enumValue(record, "adjustment_type", ["void", "replace"] as const, boundary);
	stringValue(record, "reason", boundary);
	stringValue(record, "created_at", boundary);
	if (record["adjustment_type"] === "replace" && typeof record["replacement_fill_id"] !== "string") {
		throw new Error("fillAdjustment.replacement_fill_id: replacement requires an identity");
	}
}

export function assertDailyDecisionV3(value: unknown): asserts value is DailyDecisionV3 {
	const boundary = "dailyDecisionV3";
	const record = recordValue(value, boundary);
	enumValue(record, "readiness", ["ready", "review", "blocked"] as const, boundary);
	const provenance = recordValue(record["provenance"], boundary, "provenance");
	for (const field of ["decision_time", "knowledge_cutoff", "publication_cutoff", "generated_at"] as const) {
		const fieldValue = provenance[field];
		if (fieldValue !== null) stringValue(provenance, field, `${boundary}.provenance`);
	}
	if (!Array.isArray(provenance["source_snapshot_ids"])) {
		throw new Error("dailyDecisionV3.provenance.source_snapshot_ids: expected an array");
	}
	const reconciliation = recordValue(record["reconciliation"], boundary, "reconciliation");
	stringValue(reconciliation, "status", `${boundary}.reconciliation`);
}

export function assertPortfolioScenarioPreview(value: unknown): asserts value is PortfolioScenarioPreview {
	const boundary = "portfolioScenarioPreview";
	const record = recordValue(value, boundary);
	enumValue(record, "baseline_kind", ["model", "paper", "manual"] as const, boundary);
	const weights = recordValue(record["proposed_weights"], boundary, "proposed_weights");
	for (const [instrument, weight] of Object.entries(weights)) {
		if (typeof weight !== "string" || !Number.isFinite(Number(weight))) {
			throw new Error(`${boundary}.proposed_weights.${instrument}: expected a finite decimal string`);
		}
	}
	recordValue(record["risk"], boundary, "risk");
	if (!Array.isArray(record["applied_constraints"])) {
		throw new Error(`${boundary}.applied_constraints: expected an array`);
	}
}
