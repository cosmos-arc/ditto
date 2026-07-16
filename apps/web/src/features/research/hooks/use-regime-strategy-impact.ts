import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRegimeStrategyImpactResponse } from "@/types";

export function useRegimeStrategyImpact() {
	return useQuery({
		queryKey: ["research", "regime", "strategy-impact"],
		queryFn: () => apiClient.get<GetRegimeStrategyImpactResponse>("/research/regime/strategy-impact"),
	});
}
