import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/api";
import { strategyKeys } from "../api/query-keys";
import { fetchActive } from "../api/strategies";

/**
 * 读取策略 active pointer（`GET /api/v1/strategies/{id}/active`）。
 *
 * 无 active 版本时后端返 404——此 hook 对 404 不重试、不抛（`data` 为 undefined），
 * 供 reactivate 的 `expected_pointer_revision` 取值（null 时隐藏 reactivate）。
 */
export function useStrategyActive(strategyId: string) {
	return useQuery({
		queryKey: strategyKeys.active(strategyId),
		queryFn: () => fetchActive(strategyId),
		retry: (failureCount, error) => {
			if (error instanceof ApiError && error.status === 404) return false;
			return failureCount < 2;
		},
		throwOnError: false,
	});
}
