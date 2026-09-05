import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";
import { resolveTradingExecutionScope } from "./execution-scope";
import { DEFAULT_STRATEGY_ID } from "./query-keys";
import { assertDailyDecisionV3 } from "./runtime-validation";

export type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];
export type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
export type DailyDecisionV3Response = components["schemas"]["DailyDecisionV3Response"];
export type DailyDecisionAction = components["schemas"]["DailyDecisionActionResponse"];
export type DailyDecisionReasonCode = DailyDecisionV2Response["readiness"]["reason_codes"][number];
export type TradeIntentResponse = components["schemas"]["TradeIntentResponse"];

export type FetchDailyDecisionParams = {
	readonly strategyId?: string | undefined;
	readonly accountId?: string | undefined;
	readonly tradeDate?: string | undefined;
};

export function fetchDailyDecision(params: FetchDailyDecisionParams = {}): Promise<DailyDecisionReportResponse> {
	const { strategyId = DEFAULT_STRATEGY_ID, tradeDate } = params;

	return apiClient.get("/api/v1/manual/daily-decision", {
		params: {
			query: {
				strategy_id: strategyId,
				...(tradeDate ? { trade_date: tradeDate } : {}),
			},
		},
	});
}

export function fetchDailyDecisionV2(params: FetchDailyDecisionParams = {}): Promise<DailyDecisionV2Response> {
	const { strategyId, accountId, tradeDate } = resolveTradingExecutionScope(params);

	return apiClient.get("/api/v1/manual/daily-decision/v2", {
		params: {
			query: {
				strategy_id: strategyId,
				...(tradeDate ? { trade_date: tradeDate } : {}),
				...(accountId ? { account_id: accountId } : {}),
			},
		},
	});
}

export async function fetchDailyDecisionV3(params: FetchDailyDecisionParams = {}): Promise<DailyDecisionV3Response> {
	const { strategyId, accountId, tradeDate } = resolveTradingExecutionScope(params);
	const decision = await apiClient.get("/api/v1/manual/daily-decision/v3", {
		params: {
			query: {
				strategy_id: strategyId,
				...(tradeDate ? { trade_date: tradeDate } : {}),
				...(accountId ? { account_id: accountId } : {}),
			},
		},
	});
	assertDailyDecisionV3(decision);
	return decision;
}
