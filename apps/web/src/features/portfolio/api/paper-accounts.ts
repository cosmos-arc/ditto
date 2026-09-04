import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type PaperAccountLedger = components["schemas"]["PaperAccountLedgerResponse"];
export type PaperAccountReceipt = components["schemas"]["PaperAccountReceiptResponse"];
export type PaperExecutionReceipt = components["schemas"]["PaperExecutionReceiptResponse"];
export type PaperReconciliation = components["schemas"]["PaperReconciliationResponse"];
export type PaperRecoverReceipt = components["schemas"]["PaperRecoverResponse"];
export type PaperSessionCommandReceipt = components["schemas"]["PaperSessionCommandResponse"];
export type PaperSessionRead = components["schemas"]["PaperSessionReadResponse"];
export type CreatePaperAccountBody = components["schemas"]["CreatePaperAccountBody"];
export type CreatePaperSessionBody = components["schemas"]["CreatePaperSessionBody"];
export type OperatePaperOrderBody = components["schemas"]["OperatePaperOrderBody"];
export type PausePaperSessionBody = components["schemas"]["PausePaperSessionBody"];
export type ReconcilePaperSessionBody = components["schemas"]["ReconcilePaperSessionBody"];
export type RecoverPaperSessionBody = components["schemas"]["RecoverPaperSessionBody"];

function accountPath(accountId: string, suffix: string): string {
	return `/v1/paper/accounts/${encodeURIComponent(accountId)}${suffix}`;
}

function sessionPath(sessionId: string, suffix = ""): string {
	return `/v1/paper/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

export function createPaperAccount(body: CreatePaperAccountBody): Promise<PaperAccountReceipt> {
	return apiClient.post<PaperAccountReceipt>("/v1/paper/accounts", body);
}

export function fetchPaperAccountLedger(accountId: string, asOf: string): Promise<PaperAccountLedger> {
	return apiClient.get<PaperAccountLedger>(withQueryParams(accountPath(accountId, "/ledger"), { as_of: asOf }));
}

export function createPaperSession(body: CreatePaperSessionBody): Promise<PaperSessionCommandReceipt> {
	return apiClient.post<PaperSessionCommandReceipt>("/v1/paper/sessions", body);
}

export function fetchPaperSession(sessionId: string): Promise<PaperSessionRead> {
	return apiClient.get<PaperSessionRead>(sessionPath(sessionId));
}

export function operatePaperOrder(sessionId: string, body: OperatePaperOrderBody): Promise<PaperExecutionReceipt> {
	return apiClient.post<PaperExecutionReceipt>(sessionPath(sessionId, "/orders"), body);
}

export function pausePaperSession(sessionId: string, body: PausePaperSessionBody): Promise<PaperSessionCommandReceipt> {
	return apiClient.post<PaperSessionCommandReceipt>(sessionPath(sessionId, "/pause"), body);
}

export function reconcilePaperSession(
	sessionId: string,
	body: ReconcilePaperSessionBody,
): Promise<PaperReconciliation> {
	return apiClient.post<PaperReconciliation>(sessionPath(sessionId, "/reconcile"), body);
}

export function recoverPaperSession(sessionId: string, body: RecoverPaperSessionBody): Promise<PaperRecoverReceipt> {
	return apiClient.post<PaperRecoverReceipt>(sessionPath(sessionId, "/recover"), body);
}
