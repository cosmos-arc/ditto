import { useQuery } from "@tanstack/react-query";
import { mapStrategyVersionDetail } from "../api/mappers";
import { strategyKeys } from "../api/query-keys";
import { fetchStrategyVersionDetail } from "../api/strategies";

/** 读取用户显式选中的 immutable 历史版本。null 时不发请求。 */
export function useStrategyVersion(strategyId: string, version: number | null) {
	return useQuery({
		queryKey: strategyKeys.version(strategyId, version ?? 0),
		queryFn: () => fetchStrategyVersionDetail(strategyId, version as number).then(mapStrategyVersionDetail),
		enabled: version !== null,
	});
}
