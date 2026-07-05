import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalDetailResponse } from "@/types";
import { mapDailyDecisionToSignalDetail } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecision } from "./use-daily-decision";

export function useSignalDetail(id: string) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecision(
		undefined,
		(report) => mapDailyDecisionToSignalDetail(report, id),
		{ enabled: !usePrototypeMocks },
	);
	const mockQuery = useQuery({
		queryKey: ["trading", "signals", id],
		queryFn: () => apiClient.get<GetSignalDetailResponse>(`/trading/signals/${id}`),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
