import { useQuery } from "@tanstack/react-query";
import { type FetchDailyDecisionParams, fetchDailyDecisionV3 } from "../api/daily-decision";
import { resolveTradingExecutionScope } from "../api/execution-scope";
import { mapDailyDecisionV3 } from "../api/mappers";
import { tradingKeys } from "../api/query-keys";

export function useDailyDecisionV3(
	params: FetchDailyDecisionParams = {},
	options: { readonly enabled?: boolean } = {},
) {
	const { strategyId, accountId, tradeDate } = resolveTradingExecutionScope(params);

	return useQuery({
		queryKey: tradingKeys.dailyDecisionV3(strategyId, tradeDate, accountId),
		queryFn: () => fetchDailyDecisionV3({ strategyId, accountId, tradeDate }),
		select: mapDailyDecisionV3,
		enabled: options.enabled ?? true,
	});
}
