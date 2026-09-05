import { useQuery } from "@tanstack/react-query";
import type { SpecDiff } from "@/types/strategy";
import { mapSpecDiff } from "../api/mappers";
import { strategyKeys } from "../api/query-keys";
import { fetchVersionDiff } from "../api/strategies";

/** 读取版本 vs parent 的字段级 canonical spec diff。 */
export function useVersionDiff(strategyId: string, version: number, enabled = true) {
	return useQuery({
		queryKey: strategyKeys.diff(strategyId, version),
		queryFn: () => fetchVersionDiff(strategyId, version).then(mapSpecDiff),
		enabled,
	});
}

export type { SpecDiff };
