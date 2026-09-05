import { useQuery } from "@tanstack/react-query";
import {
	type DailyDecisionReportResponse,
	type FetchDailyDecisionParams,
	fetchDailyDecision,
} from "../api/daily-decision";
import { DEFAULT_STRATEGY_ID, tradingKeys } from "../api/query-keys";

export function useDailyDecision<TData = DailyDecisionReportResponse>(
	params: FetchDailyDecisionParams = {},
	select?: (report: DailyDecisionReportResponse) => TData,
	options: { readonly enabled?: boolean } = {},
) {
	const { strategyId = DEFAULT_STRATEGY_ID, tradeDate } = params;

	return useQuery({
		queryKey: tradingKeys.dailyDecision(strategyId, tradeDate),
		queryFn: () => fetchDailyDecision({ strategyId, tradeDate }),
		...(select === undefined ? {} : { select }),
		enabled: options.enabled ?? true,
	});
}
