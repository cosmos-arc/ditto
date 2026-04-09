import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetAgentFindingsResponse, GetAgentRunsResponse } from "@/types";

export function useAgentRuns() {
	return useQuery({
		queryKey: ["ai", "agents", "runs"],
		queryFn: () => apiClient.get<GetAgentRunsResponse>("/agents/runs"),
	});
}

export function useAgentFindings() {
	return useQuery({
		queryKey: ["ai", "agents", "findings"],
		queryFn: () => apiClient.get<GetAgentFindingsResponse>("/ai/agents/findings"),
	});
}
