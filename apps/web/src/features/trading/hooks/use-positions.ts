import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetPositionsResponse } from "@/types";
import { mapPositionsResponse } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecision } from "./use-daily-decision";

export function usePositions() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecision(undefined, mapPositionsResponse, {
		enabled: !usePrototypeMocks,
	});
	const mockQuery = useQuery({
		queryKey: ["trading", "positions"],
		queryFn: () => apiClient.get<GetPositionsResponse>("/trading/positions"),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
