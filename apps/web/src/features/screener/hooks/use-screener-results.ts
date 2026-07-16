import { useQuery } from "@tanstack/react-query";
import { apiClient, withQueryParams } from "@/lib/api-client";
import type { RunScreenerRequest, RunScreenerResponse } from "@/types";

export function useScreenerResults(filters?: RunScreenerRequest) {
	return useQuery({
		queryKey: ["screener", "results", filters],
		queryFn: () => apiClient.get<RunScreenerResponse>(withQueryParams("/screener/run", filters)),
	});
}
