import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetOrdersRequest, GetOrdersResponse } from "@/types";

function buildOrdersQuery(params?: GetOrdersRequest): string {
	if (!params) return "/trading/orders";

	const searchParams = new URLSearchParams();
	if (params.tab) searchParams.set("tab", params.tab);
	if (params.page) searchParams.set("page", String(params.page));
	if (params.limit) searchParams.set("limit", String(params.limit));
	if (params.pageSize) searchParams.set("pageSize", String(params.pageSize));
	if (params.sort) searchParams.set("sort", params.sort);

	const qs = searchParams.toString();
	return qs ? `/trading/orders?${qs}` : "/trading/orders";
}

export function useOrders(params?: GetOrdersRequest) {
	return useQuery({
		queryKey: ["trading", "orders", params],
		queryFn: () => apiClient.get<GetOrdersResponse>(buildOrdersQuery(params)),
	});
}
