import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetStrategyVersionsResponse } from "@/types";

export function useStrategyVersions(id: string) {
	return useQuery({
		queryKey: ["strategy", id, "versions"],
		queryFn: () => apiClient.get<GetStrategyVersionsResponse>(`/strategies/${id}/versions`),
	});
}
