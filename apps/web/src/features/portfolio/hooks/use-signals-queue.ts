import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalsQueueResponse } from "@/types";
import { mapDailyDecisionToSignalsQueue, mapDailyDecisionV2ToLegacy } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function useSignalsQueue() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(
		undefined,
		(report) => mapDailyDecisionToSignalsQueue(mapDailyDecisionV2ToLegacy(report)),
		{
			enabled: !usePrototypeMocks,
		},
	);
	const mockQuery = useQuery({
		queryKey: ["trading", "signals", "queue"],
		queryFn: () => apiClient.get<GetSignalsQueueResponse>("/portfolio/review/queue"),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
