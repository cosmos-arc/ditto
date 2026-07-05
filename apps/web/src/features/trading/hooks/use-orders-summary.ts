import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetOrdersSummaryResponse } from "@/types";
import { mapDailyDecisionToOrdersSummary } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecision } from "./use-daily-decision";

export function useOrdersSummary() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecision(undefined, mapDailyDecisionToOrdersSummary, {
		enabled: !usePrototypeMocks,
	});
	const mockQuery = useQuery({
		queryKey: ["trading", "orders", "summary"],
		queryFn: () => apiClient.get<GetOrdersSummaryResponse>("/trading/orders/summary"),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
