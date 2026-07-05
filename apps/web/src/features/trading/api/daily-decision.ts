import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import { DEFAULT_STRATEGY_ID } from "./query-keys";

export type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];

export type FetchDailyDecisionParams = {
	readonly strategyId?: string;
	readonly tradeDate?: string;
};

export function fetchDailyDecision(
	params: FetchDailyDecisionParams = {},
): Promise<DailyDecisionReportResponse> {
	const { strategyId = DEFAULT_STRATEGY_ID, tradeDate } = params;

	return apiClient.get<DailyDecisionReportResponse>(
		withQueryParams("/v1/trade/daily-decision", {
			strategy_id: strategyId,
			trade_date: tradeDate,
		}),
	);
}
