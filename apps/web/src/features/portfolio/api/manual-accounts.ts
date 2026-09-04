import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type ManualAccount = components["schemas"]["AccountResponse"];
export type ManualAccountEvent = components["schemas"]["AccountEventResponse"];
export type ManualAccountLedger = components["schemas"]["AccountLedgerResponse"];
export type ManualAccountReceipt = components["schemas"]["AccountCommandReceiptResponse"];
export type CreateManualAccountBody = components["schemas"]["CreateManualAccountBody"];
export type ManualEventBody = components["schemas"]["ManualEventBody"];
export type ManualBusinessEventType = components["schemas"]["ManualBusinessEventType"];
export type CorrectManualEventBody = components["schemas"]["CorrectManualEventBody"];
export type ReverseManualEventBody = components["schemas"]["ReverseManualEventBody"];

function accountPath(accountId: string, suffix: string): string {
	return `/v1/manual/accounts/${encodeURIComponent(accountId)}${suffix}`;
}

export function createManualAccount(body: CreateManualAccountBody): Promise<ManualAccountReceipt> {
	return apiClient.post<ManualAccountReceipt>("/v1/manual/accounts", body);
}

export function fetchManualAccountLedger(accountId: string, asOf: string): Promise<ManualAccountLedger> {
	return apiClient.get<ManualAccountLedger>(withQueryParams(accountPath(accountId, "/ledger"), { as_of: asOf }));
}

export function recordManualAccountEvent(accountId: string, body: ManualEventBody): Promise<ManualAccountReceipt> {
	return apiClient.post<ManualAccountReceipt>(accountPath(accountId, "/events"), body);
}

export function correctManualAccountEvent(
	accountId: string,
	body: CorrectManualEventBody,
): Promise<ManualAccountReceipt> {
	return apiClient.post<ManualAccountReceipt>(accountPath(accountId, "/corrections"), body);
}

export function reverseManualAccountEvent(
	accountId: string,
	body: ReverseManualEventBody,
): Promise<ManualAccountReceipt> {
	return apiClient.post<ManualAccountReceipt>(accountPath(accountId, "/reversals"), body);
}
