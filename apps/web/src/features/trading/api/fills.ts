import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import { DEFAULT_STRATEGY_ID } from "./query-keys";

export type FillResponse = components["schemas"]["FillResponse"];
export type RecordFillRequest = components["schemas"]["RecordFillRequest"];

export interface FetchFillsParams {
	readonly strategyId?: string;
	readonly startDate?: string;
	readonly endDate?: string;
}

export function fetchFills(params: FetchFillsParams = {}): Promise<readonly FillResponse[]> {
	const { strategyId = DEFAULT_STRATEGY_ID, startDate, endDate } = params;

	return apiClient.get<readonly FillResponse[]>(
		withQueryParams("/v1/trade/fills", {
			strategy_id: strategyId,
			start_date: startDate,
			end_date: endDate,
		}),
	);
}

export function recordFill(payload: RecordFillRequest): Promise<FillResponse> {
	return apiClient.post<FillResponse>("/v1/trade/fills", payload);
}
