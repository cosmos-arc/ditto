import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetAgentQuickViewResponse } from "@/types";

export function useAgentQuickView() {
	return useQuery({
		queryKey: ["ai", "agents", "quick-view"],
		queryFn: () => apiClient.get<GetAgentQuickViewResponse>("/ai/agents/quick-view"),
	});
}
