import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetCopilotQuickViewResponse, GetCopilotSessionsResponse } from "@/types";

export function useCopilotQuickView() {
	return useQuery({
		queryKey: ["ai", "copilot", "quick-view"],
		queryFn: () => apiClient.get<GetCopilotQuickViewResponse>("/ai/copilot/quick-view"),
	});
}

export function useCopilotSessions() {
	return useQuery({
		queryKey: ["ai", "copilot", "sessions"],
		queryFn: () => apiClient.get<GetCopilotSessionsResponse>("/ai/copilot/sessions"),
	});
}
