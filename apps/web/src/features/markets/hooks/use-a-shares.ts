import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { ASharesOverviewResponse } from "@/types";

export function useAShares() {
	return useQuery({
		queryKey: ["markets", "a-shares"],
		queryFn: () => apiClient.get<ASharesOverviewResponse>("/markets/a-shares"),
	});
}
