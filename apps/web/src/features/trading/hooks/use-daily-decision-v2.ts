import { useQuery } from "@tanstack/react-query";
import {
	type DailyDecisionV2Response,
	type FetchDailyDecisionParams,
	fetchDailyDecisionV2,
} from "../api/daily-decision";
import { resolveTradingExecutionScope } from "../api/execution-scope";
import { tradingKeys } from "../api/query-keys";

export function useDailyDecisionV2<TData = DailyDecisionV2Response>(
	params: FetchDailyDecisionParams = {},
	select?: (report: DailyDecisionV2Response) => TData,
	options: { readonly enabled?: boolean } = {},
) {
	const { strategyId, accountId, tradeDate } = resolveTradingExecutionScope(params);

	return useQuery({
		queryKey: [...tradingKeys.dailyDecision(strategyId, tradeDate, accountId), "v2"],
		queryFn: () => fetchDailyDecisionV2({ strategyId, accountId, tradeDate }),
		select,
		enabled: options.enabled,
	});
}
