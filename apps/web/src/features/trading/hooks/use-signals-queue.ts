import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { SignalsQueueResponse } from "@/types";

export function useSignalsQueue() {
	return useQuery({
		queryKey: ["trading", "signals", "queue"],
		queryFn: () => apiClient.get<SignalsQueueResponse>("/trading/signals/queue"),
	});
}
