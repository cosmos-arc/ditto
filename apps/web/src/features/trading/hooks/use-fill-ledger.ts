import { useQuery } from "@tanstack/react-query";
import {
	fetchFillLedger,
} from "../api/fill-ledger";
import type { FetchFillsParams } from "../api/fills";
import { DEFAULT_STRATEGY_ID, tradingKeys } from "../api/query-keys";

export function useFillLedger(
	params: FetchFillsParams = {},
	options: { readonly enabled?: boolean } = {},
) {
	const { strategyId = DEFAULT_STRATEGY_ID, startDate, endDate } = params;

	return useQuery({
		queryKey: tradingKeys.fills(strategyId, startDate, endDate),
		queryFn: () => fetchFillLedger({ strategyId, startDate, endDate }),
		enabled: options.enabled,
	});
}
