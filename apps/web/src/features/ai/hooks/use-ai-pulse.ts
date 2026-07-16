import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { AiPulseResponse } from "@/types";

export function useAiPulse() {
	return useQuery({
		queryKey: ["ai", "pulse"],
		queryFn: () => apiClient.get<AiPulseResponse>("/ai/pulse"),
	});
}
