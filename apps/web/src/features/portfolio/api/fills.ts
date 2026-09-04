import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import { DEFAULT_STRATEGY_ID } from "./query-keys";

export type FillResponse = components["schemas"]["FillResponse"];
export type FillAdjustmentResponse = components["schemas"]["FillAdjustmentResponse"];
export type RecordFillRequest = components["schemas"]["RecordFillRequest"];
export type ReplaceFillRequest = components["schemas"]["ReplaceFillRequest"];
export type VoidFillRequest = components["schemas"]["VoidFillRequest"];

export interface FetchFillsParams {
	readonly strategyId?: string;
	readonly startDate?: string;
	readonly endDate?: string;
}

export interface FetchFillAdjustmentsParams {
	readonly strategyId?: string;
	readonly fillId?: string;
	readonly intentId?: string;
}

export function fetchFills(params: FetchFillsParams = {}): Promise<readonly FillResponse[]> {
	const { strategyId = DEFAULT_STRATEGY_ID, startDate, endDate } = params;

	return apiClient.get<readonly FillResponse[]>(
		withQueryParams("/v1/manual/fills", {
			strategy_id: strategyId,
			start_date: startDate,
			end_date: endDate,
		}),
	);
}

export function fetchEffectiveFills(params: FetchFillsParams = {}): Promise<readonly FillResponse[]> {
	const { strategyId = DEFAULT_STRATEGY_ID, startDate, endDate } = params;

	return apiClient.get<readonly FillResponse[]>(
		withQueryParams("/v1/manual/fills/effective", {
			strategy_id: strategyId,
			start_date: startDate,
			end_date: endDate,
		}),
	);
}

export function fetchFillAdjustments(
	params: FetchFillAdjustmentsParams = {},
): Promise<readonly FillAdjustmentResponse[]> {
	const { strategyId = DEFAULT_STRATEGY_ID, fillId, intentId } = params;

	return apiClient.get<readonly FillAdjustmentResponse[]>(
		withQueryParams("/v1/manual/fill-adjustments", {
			strategy_id: strategyId,
			fill_id: fillId,
			intent_id: intentId,
		}),
	);
}

export function recordFill(payload: RecordFillRequest): Promise<FillResponse> {
	return apiClient.post<FillResponse>("/v1/manual/fills", payload);
}

export function voidFill(fillId: string, payload: VoidFillRequest): Promise<FillAdjustmentResponse> {
	return apiClient.post<FillAdjustmentResponse>(`/v1/manual/fills/${encodeURIComponent(fillId)}/void`, payload);
}

export function replaceFill(fillId: string, payload: ReplaceFillRequest): Promise<FillAdjustmentResponse> {
	return apiClient.post<FillAdjustmentResponse>(`/v1/manual/fills/${encodeURIComponent(fillId)}/replace`, payload);
}
