import { apiClient } from "@/api/transport";
import type {
	CreatePaperAccountBody,
	CreatePaperSessionBody,
	ManualHistoryQueryIdentity,
	OperatePaperOrderBody,
	PaperAccountHistory,
	PaperAccountLedger,
	PaperAccountReceipt,
	PaperExecutionReceipt,
	PaperReconciliation,
	PaperRecoverReceipt,
	PaperSessionCommandReceipt,
	PaperSessionRead,
	PausePaperSessionBody,
	ReconcilePaperSessionBody,
	RecoverPaperSessionBody,
} from "./account-models";
import {
	parsePaperAccountHistory,
	parsePaperAccountLedger,
	parsePaperAccountReceipt,
	parsePaperExecutionReceipt,
	parsePaperReconciliation,
	parsePaperRecoverReceipt,
	parsePaperSessionCommandReceipt,
	parsePaperSessionRead,
} from "./runtime-validation";

export type {
	CreatePaperAccountBody,
	CreatePaperSessionBody,
	ManualHistoryQueryIdentity,
	OperatePaperOrderBody,
	PaperAccountHistory,
	PaperAccountLedger,
	PaperAccountReceipt,
	PaperExecutionReceipt,
	PaperReconciliation,
	PaperRecoverReceipt,
	PaperSessionCommandReceipt,
	PaperSessionRead,
	PausePaperSessionBody,
	ReconcilePaperSessionBody,
	RecoverPaperSessionBody,
} from "./account-models";

export async function createPaperAccount(body: CreatePaperAccountBody): Promise<PaperAccountReceipt> {
	const payload = await apiClient.post("/api/v1/paper/accounts", { body });
	return parsePaperAccountReceipt(payload, body.account_id);
}

export async function fetchPaperAccountLedger(accountId: string, asOf: string): Promise<PaperAccountLedger> {
	const payload = await apiClient.get("/api/v1/paper/accounts/{account_id}/ledger", {
		params: { path: { account_id: accountId }, query: { as_of: asOf } },
	});
	return parsePaperAccountLedger(payload, accountId, asOf);
}

export async function fetchPaperAccountHistory(
	accountId: string,
	sessionId: string,
	identity: ManualHistoryQueryIdentity,
): Promise<PaperAccountHistory> {
	const payload = await apiClient.get("/api/v1/paper/accounts/{account_id}/history", {
		params: {
			path: { account_id: accountId },
			query: {
				session_id: sessionId,
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
	return parsePaperAccountHistory(payload, accountId, identity);
}

export async function createPaperSession(body: CreatePaperSessionBody): Promise<PaperSessionCommandReceipt> {
	const payload = await apiClient.post("/api/v1/paper/sessions", { body });
	return parsePaperSessionCommandReceipt(payload, body.session_id, body.start_immediately ? "start" : "create");
}

export async function fetchPaperSession(sessionId: string): Promise<PaperSessionRead> {
	const payload = await apiClient.get("/api/v1/paper/sessions/{session_id}", {
		params: { path: { session_id: sessionId } },
	});
	return parsePaperSessionRead(payload, sessionId);
}

export async function operatePaperOrder(
	sessionId: string,
	body: OperatePaperOrderBody,
): Promise<PaperExecutionReceipt> {
	const payload = await apiClient.post("/api/v1/paper/sessions/{session_id}/orders", {
		body,
		params: { path: { session_id: sessionId } },
	});
	return parsePaperExecutionReceipt(payload, {
		direction: body.side,
		idempotencyKey: body.idempotency_key,
		instrumentId: body.instrument_id,
		orderId: body.order_id,
		settlementDate: body.settlement_date,
		tradeDate: body.trade_date,
	});
}

export async function pausePaperSession(
	sessionId: string,
	body: PausePaperSessionBody,
): Promise<PaperSessionCommandReceipt> {
	const payload = await apiClient.post("/api/v1/paper/sessions/{session_id}/pause", {
		body,
		params: { path: { session_id: sessionId } },
	});
	return parsePaperSessionCommandReceipt(payload, sessionId, "pause");
}

export async function reconcilePaperSession(
	sessionId: string,
	body: ReconcilePaperSessionBody,
): Promise<PaperReconciliation> {
	const payload = await apiClient.post("/api/v1/paper/sessions/{session_id}/reconcile", {
		body,
		params: { path: { session_id: sessionId } },
	});
	return parsePaperReconciliation(payload, sessionId);
}

export async function recoverPaperSession(
	sessionId: string,
	body: RecoverPaperSessionBody,
): Promise<PaperRecoverReceipt> {
	const payload = await apiClient.post("/api/v1/paper/sessions/{session_id}/recover", {
		body,
		params: { path: { session_id: sessionId } },
	});
	return parsePaperRecoverReceipt(payload, body.idempotency_key);
}
