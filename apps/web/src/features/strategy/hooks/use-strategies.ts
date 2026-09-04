import { useQuery } from "@tanstack/react-query";
import type { StrategyListItem } from "@/types/strategy";
import { mapStrategyListItem } from "../api/mappers";
import { strategyKeys } from "../api/query-keys";
import { type FetchStrategiesParams, fetchStrategies } from "../api/strategies";

/** 列出策略（`GET /v1/strategies`）。 */
export function useStrategies(params: FetchStrategiesParams = {}) {
	return useQuery({
		queryKey: strategyKeys.list(params.limit, params.offset),
		queryFn: async () => (await fetchStrategies(params)).map(mapStrategyListItem),
	});
}

export type { StrategyListItem };
