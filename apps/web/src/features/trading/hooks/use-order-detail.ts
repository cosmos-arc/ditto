import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetOrderDetailResponse } from "@/types";

export function useOrderDetail(id: string) {
	return useQuery({
		queryKey: ["trading", "orders", id],
		queryFn: () => apiClient.get<GetOrderDetailResponse>(`/trading/orders/${id}`),
	});
}
