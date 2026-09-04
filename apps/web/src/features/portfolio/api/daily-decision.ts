import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import { resolveTradingExecutionScope } from "./execution-scope";
import { DEFAULT_STRATEGY_ID } from "./query-keys";

export type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];
export type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
export type DailyDecisionV3Response = components["schemas"]["DailyDecisionV3Response"];

export type FetchDailyDecisionParams = {
	readonly strategyId?: string;
	readonly accountId?: string;
	readonly tradeDate?: string;
};

export function fetchDailyDecision(params: FetchDailyDecisionParams = {}): Promise<DailyDecisionReportResponse> {
	const { strategyId = DEFAULT_STRATEGY_ID, tradeDate } = params;

	return apiClient.get<DailyDecisionReportResponse>(
		withQueryParams("/v1/manual/daily-decision", {
			strategy_id: strategyId,
			trade_date: tradeDate,
		}),
	);
}

export function fetchDailyDecisionV2(params: FetchDailyDecisionParams = {}): Promise<DailyDecisionV2Response> {
	const { strategyId, accountId, tradeDate } = resolveTradingExecutionScope(params);

	return apiClient.get<DailyDecisionV2Response>(
		withQueryParams("/v1/manual/daily-decision/v2", {
			strategy_id: strategyId,
			trade_date: tradeDate,
			account_id: accountId,
		}),
	);
}

export function fetchDailyDecisionV3(params: FetchDailyDecisionParams = {}): Promise<DailyDecisionV3Response> {
	const { strategyId, accountId, tradeDate } = resolveTradingExecutionScope(params);

	return apiClient.get<DailyDecisionV3Response>(
		withQueryParams("/v1/manual/daily-decision/v3", {
			strategy_id: strategyId,
			trade_date: tradeDate,
			account_id: accountId,
		}),
	);
}
