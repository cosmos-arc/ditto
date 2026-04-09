import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetAgentPlansResponse } from "@/types";

export function useAgentPlans() {
	return useQuery({
		queryKey: ["ai", "agents", "plans"],
		queryFn: () => apiClient.get<GetAgentPlansResponse>("/ai/agents/plans"),
	});
}
