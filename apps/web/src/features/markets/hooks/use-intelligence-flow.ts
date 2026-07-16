import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetIntelligenceFlowResponse } from "@/types";

export function useIntelligenceFlow() {
	return useQuery({
		queryKey: ["markets", "intelligence", "flow"],
		queryFn: () => apiClient.get<GetIntelligenceFlowResponse>("/markets/intelligence/flow"),
	});
}
