import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetOrdersSummaryResponse } from "@/types";

export function useOrdersSummary() {
	return useQuery({
		queryKey: ["trading", "orders", "summary"],
		queryFn: () => apiClient.get<GetOrdersSummaryResponse>("/trading/orders/summary"),
	});
}
