import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRegimeHistoryResponse, PaginatedRequest } from "@/types";

export function useRegimeHistory(params?: PaginatedRequest) {
	return useQuery({
		queryKey: ["research", "regime", "history", params],
		queryFn: () => apiClient.get<GetRegimeHistoryResponse>("/research/regime/history", params),
	});
}
