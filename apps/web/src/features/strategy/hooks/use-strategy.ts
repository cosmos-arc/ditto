import { useQuery } from "@tanstack/react-query";
import type { StrategyDetail } from "@/types/strategy";
import { mapStrategyDetail } from "../api/mappers";
import { strategyKeys } from "../api/query-keys";
import { fetchStrategy } from "../api/strategies";

/** 读取单个策略详情（顶层 + legacy spec 展开）。 */
export function useStrategy(id: string) {
	return useQuery({
		queryKey: strategyKeys.detail(id),
		queryFn: () => fetchStrategy(id).then(mapStrategyDetail),
	});
}

export type { StrategyDetail };
