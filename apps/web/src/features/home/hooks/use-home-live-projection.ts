import { useQuery } from "@tanstack/react-query";
import { fetchDailyDecisionV3 } from "@/features/portfolio/api/daily-decision";
import { resolveTradingExecutionScope } from "@/features/portfolio/api/execution-scope";
import { tradingKeys } from "@/features/portfolio/api/query-keys";
import { type HomeLiveProjection, mapDailyDecisionV3ToHomeProjection } from "../api/home-projection";

export function useHomeLiveProjection<T>(
	select: (projection: HomeLiveProjection) => T,
	options: { readonly enabled: boolean },
) {
	const { strategyId, accountId, tradeDate } = resolveTradingExecutionScope();

	return useQuery({
		queryKey: tradingKeys.dailyDecisionV3(strategyId, tradeDate, accountId),
		queryFn: () => fetchDailyDecisionV3({ strategyId, accountId, tradeDate }),
		select: (report) => select(mapDailyDecisionV3ToHomeProjection(report)),
		enabled: options.enabled,
	});
}
