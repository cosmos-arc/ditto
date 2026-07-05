import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalsQueueResponse } from "@/types";
import { mapDailyDecisionToSignalsQueue } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecision } from "./use-daily-decision";

export function useSignalsQueue() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecision(undefined, mapDailyDecisionToSignalsQueue, {
		enabled: !usePrototypeMocks,
	});
	const mockQuery = useQuery({
		queryKey: ["trading", "signals", "queue"],
		queryFn: () => apiClient.get<GetSignalsQueueResponse>("/trading/signals/queue"),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
