import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetStrategyResponse } from "@/types";

export function useStrategy(id: string) {
	return useQuery({
		queryKey: ["strategy", id],
		queryFn: () => apiClient.get<GetStrategyResponse>(`/strategies/${id}`),
	});
}
