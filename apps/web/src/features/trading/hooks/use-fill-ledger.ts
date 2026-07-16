import { useQuery } from "@tanstack/react-query";
import { resolveTradingExecutionScope } from "../api/execution-scope";
import { fetchFillLedger } from "../api/fill-ledger";
import type { FetchFillsParams } from "../api/fills";
import { tradingKeys } from "../api/query-keys";

export function useFillLedger(params: FetchFillsParams = {}, options: { readonly enabled?: boolean } = {}) {
	const { strategyId } = resolveTradingExecutionScope({ strategyId: params.strategyId });
	const { startDate, endDate } = params;

	return useQuery({
		queryKey: tradingKeys.fills(strategyId, startDate, endDate),
		queryFn: () => fetchFillLedger({ strategyId, startDate, endDate }),
		enabled: options.enabled,
	});
}
