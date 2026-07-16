import { useQuery } from "@tanstack/react-query";
import { apiClient, withQueryParams } from "@/lib/api-client";
import type { GetMarketCalendarResponse, PaginatedRequest } from "@/types";

export function useMarketCalendar(params?: PaginatedRequest) {
	return useQuery({
		queryKey: ["markets", "calendar", params],
		queryFn: () => apiClient.get<GetMarketCalendarResponse>(withQueryParams("/market/calendar", params)),
	});
}
