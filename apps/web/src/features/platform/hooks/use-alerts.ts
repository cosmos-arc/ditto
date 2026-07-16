import { useQuery } from "@tanstack/react-query";
import { apiClient, withQueryParams } from "@/lib/api-client";
import type { GetPlatformAlertsResponse, PaginatedRequest } from "@/types";

export function usePlatformAlerts(params?: PaginatedRequest) {
	return useQuery({
		queryKey: ["platform", "alerts", params],
		queryFn: () => apiClient.get<GetPlatformAlertsResponse>(withQueryParams("/platform/alerts", params)),
	});
}
