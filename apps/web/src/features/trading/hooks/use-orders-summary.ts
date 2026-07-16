import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetOrdersSummaryResponse } from "@/types";
import { mapDailyDecisionToOrdersSummary, mapDailyDecisionV2ToLegacy } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function useOrdersSummary() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(
		undefined,
		(report) => mapDailyDecisionToOrdersSummary(mapDailyDecisionV2ToLegacy(report)),
		{
			enabled: !usePrototypeMocks,
		},
	);
	const mockQuery = useQuery({
		queryKey: ["trading", "orders", "summary"],
		queryFn: () => apiClient.get<GetOrdersSummaryResponse>("/trading/orders/summary"),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
