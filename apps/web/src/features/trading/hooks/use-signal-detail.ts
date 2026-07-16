import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalDetailResponse } from "@/types";
import { mapDailyDecisionToSignalDetail, mapDailyDecisionV2ToLegacy } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function useSignalDetail(id: string) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(
		undefined,
		(report) => mapDailyDecisionToSignalDetail(mapDailyDecisionV2ToLegacy(report), id),
		{ enabled: !usePrototypeMocks },
	);
	const mockQuery = useQuery({
		queryKey: ["trading", "signals", id],
		queryFn: () => apiClient.get<GetSignalDetailResponse>(`/trading/signals/${id}`),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
