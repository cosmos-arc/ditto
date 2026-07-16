import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalsRequest, GetSignalsResponse } from "@/types";
import { mapDailyDecisionToSignalsResponse, mapDailyDecisionV2ToLegacy } from "../api/mappers";
import { DEFAULT_STRATEGY_ID, tradingKeys } from "../api/query-keys";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

function buildSignalsQuery(params?: GetSignalsRequest): string {
	if (!params) return "/trading/signals";

	const searchParams = new URLSearchParams();
	if (params.tab) searchParams.set("tab", params.tab);
	if (params.page) searchParams.set("page", String(params.page));
	if (params.limit) searchParams.set("limit", String(params.limit));
	if (params.pageSize) searchParams.set("pageSize", String(params.pageSize));

	const qs = searchParams.toString();
	return qs ? `/trading/signals?${qs}` : "/trading/signals";
}

export function useSignals(params?: GetSignalsRequest) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(
		undefined,
		(report) => mapDailyDecisionToSignalsResponse(mapDailyDecisionV2ToLegacy(report), params),
		{ enabled: !usePrototypeMocks },
	);
	const mockQuery = useQuery({
		queryKey: tradingKeys.signals(DEFAULT_STRATEGY_ID, params?.tab),
		queryFn: () => apiClient.get<GetSignalsResponse>(buildSignalsQuery(params)),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
