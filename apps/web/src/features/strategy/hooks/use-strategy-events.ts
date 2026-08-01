import { useInfiniteQuery } from "@tanstack/react-query";
import { strategyKeys } from "../api/query-keys";
import { fetchStrategyEvents, mapStrategyGovernanceEvent } from "../api/strategies";

export function useStrategyEvents(strategyId: string, pageSize = 50) {
	return useInfiniteQuery({
		queryKey: [...strategyKeys.events(strategyId), pageSize],
		queryFn: async ({ pageParam }) =>
			(await fetchStrategyEvents(strategyId, pageParam, pageSize)).map(mapStrategyGovernanceEvent),
		initialPageParam: null as string | null,
		getNextPageParam: (page) => (page.length === pageSize ? page.at(-1)?.eventId : undefined),
		retry: false,
	});
}
