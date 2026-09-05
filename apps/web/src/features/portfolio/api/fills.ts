import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";
import { DEFAULT_STRATEGY_ID } from "./query-keys";
import { assertFillAdjustment } from "./runtime-validation";

export type FillResponse = components["schemas"]["FillResponse"];
export type FillAdjustmentResponse = components["schemas"]["FillAdjustmentResponse"];
export type RecordFillRequest = components["schemas"]["RecordFillRequest"];
export type ReplaceFillRequest = components["schemas"]["ReplaceFillRequest"];
export type VoidFillRequest = components["schemas"]["VoidFillRequest"];

export interface FetchFillsParams {
	readonly strategyId?: string | undefined;
	readonly startDate?: string | undefined;
	readonly endDate?: string | undefined;
}

export interface FetchFillAdjustmentsParams {
	readonly strategyId?: string | undefined;
	readonly fillId?: string | undefined;
	readonly intentId?: string | undefined;
}

export function fetchFills(params: FetchFillsParams = {}): Promise<readonly FillResponse[]> {
	const { strategyId = DEFAULT_STRATEGY_ID, startDate, endDate } = params;

	return apiClient.get("/api/v1/manual/fills", {
		params: {
			query: {
				strategy_id: strategyId,
				...(startDate ? { start_date: startDate } : {}),
				...(endDate ? { end_date: endDate } : {}),
			},
		},
	});
}

export function fetchEffectiveFills(params: FetchFillsParams = {}): Promise<readonly FillResponse[]> {
	const { strategyId = DEFAULT_STRATEGY_ID, startDate, endDate } = params;

	return apiClient.get("/api/v1/manual/fills/effective", {
		params: {
			query: {
				strategy_id: strategyId,
				...(startDate ? { start_date: startDate } : {}),
				...(endDate ? { end_date: endDate } : {}),
			},
		},
	});
}

export function fetchFillAdjustments(
	params: FetchFillAdjustmentsParams = {},
): Promise<readonly FillAdjustmentResponse[]> {
	const { strategyId = DEFAULT_STRATEGY_ID, fillId, intentId } = params;

	return apiClient.get("/api/v1/manual/fill-adjustments", {
		params: {
			query: {
				strategy_id: strategyId,
				...(fillId ? { fill_id: fillId } : {}),
				...(intentId ? { intent_id: intentId } : {}),
			},
		},
	});
}

export function recordFill(payload: RecordFillRequest): Promise<FillResponse> {
	return apiClient.post("/api/v1/manual/fills", { body: payload });
}

export async function voidFill(fillId: string, payload: VoidFillRequest): Promise<FillAdjustmentResponse> {
	const adjustment = await apiClient.post("/api/v1/manual/fills/{fill_id}/void", {
		body: payload,
		params: { path: { fill_id: fillId } },
	});
	assertFillAdjustment(adjustment);
	return adjustment;
}

export async function replaceFill(fillId: string, payload: ReplaceFillRequest): Promise<FillAdjustmentResponse> {
	const adjustment = await apiClient.post("/api/v1/manual/fills/{fill_id}/replace", {
		body: payload,
		params: { path: { fill_id: fillId } },
	});
	assertFillAdjustment(adjustment);
	return adjustment;
}
