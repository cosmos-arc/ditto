import { useQuery } from "@tanstack/react-query";
import {
	fetchComparisonAttribution,
	type FetchComparisonParams,
} from "../api/comparison";
import { DEFAULT_STRATEGY_ID, tradingKeys } from "../api/query-keys";

export function useComparisonAttribution(
	params: FetchComparisonParams,
	options: { readonly enabled?: boolean } = {},
) {
	const { strategyId = DEFAULT_STRATEGY_ID, runId } = params;

	return useQuery({
		queryKey: [...tradingKeys.comparison(strategyId), runId],
		queryFn: () => fetchComparisonAttribution({ strategyId, runId }),
		enabled: options.enabled ?? true,
	});
}
