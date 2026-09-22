import { apiClient } from "@/api/transport";
import type {
	CorrectManualEventBody,
	CreateManualAccountBody,
	ManualAccountHistory,
	ManualAccountLedger,
	ManualAccountReceipt,
	ManualEventBody,
	ManualHistoryQueryIdentity,
	ReverseManualEventBody,
} from "./account-models";
import { parseManualAccountHistory, parseManualAccountLedger, parseManualAccountReceipt } from "./runtime-validation";

export type {
	CorrectManualEventBody,
	CreateManualAccountBody,
	ManualAccount,
	ManualAccountEvent,
	ManualAccountHistory,
	ManualAccountLedger,
	ManualAccountReceipt,
	ManualBusinessEventType,
	ManualEventBody,
	ManualFlowPosition,
	ManualHistoryQueryIdentity,
	ManualLedgerRevision,
	ReverseManualEventBody,
} from "./account-models";

export async function createManualAccount(body: CreateManualAccountBody): Promise<ManualAccountReceipt> {
	const payload = await apiClient.post("/api/v1/manual/accounts", { body });
	return parseManualAccountReceipt(payload, { accountId: body.account_id, kind: "account" });
}

export async function fetchManualAccountLedger(accountId: string, asOf: string): Promise<ManualAccountLedger> {
	const payload = await apiClient.get("/api/v1/manual/accounts/{account_id}/ledger", {
		params: { path: { account_id: accountId }, query: { as_of: asOf } },
	});
	return parseManualAccountLedger(payload, accountId, asOf);
}

export async function fetchManualAccountHistory(
	accountId: string,
	identity: ManualHistoryQueryIdentity,
): Promise<ManualAccountHistory> {
	const payload = await apiClient.get("/api/v1/manual/accounts/{account_id}/history", {
		params: {
			path: { account_id: accountId },
			query: {
				start_date: identity.start_date,
				end_date: identity.end_date,
				knowledge_cutoff: identity.knowledge_cutoff,
				publication_cutoff: identity.publication_cutoff,
				source_snapshot_ids: [...identity.source_snapshot_ids],
				ledger_event_count: identity.ledger_event_count,
				ledger_hash: identity.ledger_hash,
			},
		},
	});
	return parseManualAccountHistory(payload, accountId, identity);
}

export async function recordManualAccountEvent(
	accountId: string,
	body: ManualEventBody,
): Promise<ManualAccountReceipt> {
	const payload = await apiClient.post("/api/v1/manual/accounts/{account_id}/events", {
		body,
		params: { path: { account_id: accountId } },
	});
	return parseManualAccountReceipt(payload, {
		accountId,
		eventType: body.event_type,
		idempotencyKey: body.idempotency_key,
		kind: "business",
	});
}

export async function correctManualAccountEvent(
	accountId: string,
	body: CorrectManualEventBody,
): Promise<ManualAccountReceipt> {
	const payload = await apiClient.post("/api/v1/manual/accounts/{account_id}/corrections", {
		body,
		params: { path: { account_id: accountId } },
	});
	return parseManualAccountReceipt(payload, {
		accountId,
		correctsEventId: body.corrects_event_id,
		idempotencyKey: body.replacement.idempotency_key,
		kind: "correction",
		replacementEventType: body.replacement.event_type,
	});
}

export async function reverseManualAccountEvent(
	accountId: string,
	body: ReverseManualEventBody,
): Promise<ManualAccountReceipt> {
	const payload = await apiClient.post("/api/v1/manual/accounts/{account_id}/reversals", {
		body,
		params: { path: { account_id: accountId } },
	});
	return parseManualAccountReceipt(payload, {
		accountId,
		idempotencyKey: body.idempotency_key,
		kind: "reversal",
		reversesEventId: body.reverses_event_id,
	});
}
