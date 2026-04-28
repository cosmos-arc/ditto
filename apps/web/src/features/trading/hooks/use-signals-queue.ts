import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalsQueueResponse } from "@/types";

export function useSignalsQueue() {
	return useQuery({
		queryKey: ["trading", "signals", "queue"],
		queryFn: () => apiClient.get<GetSignalsQueueResponse>("/trading/signals/queue"),
	});
}
