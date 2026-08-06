import { useQuery } from "@tanstack/react-query";
import type { StrategyVersion } from "@/types/strategy";
import { mapStrategyVersion } from "../api/mappers";
import { strategyKeys } from "../api/query-keys";
import { fetchStrategyVersions } from "../api/strategies";

/** 列出策略的治理版本（newest first）。 */
export function useStrategyVersions(id: string) {
	return useQuery({
		queryKey: strategyKeys.versions(id),
		queryFn: async () => (await fetchStrategyVersions(id)).map(mapStrategyVersion),
	});
}

export type { StrategyVersion };
