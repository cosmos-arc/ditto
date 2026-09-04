import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetOrdersRequest, GetOrdersResponse } from "@/types";
import { mapDailyDecisionV2ToOrdersResponse } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

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
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(undefined, (report) => mapDailyDecisionV2ToOrdersResponse(report, params), {
		enabled: !usePrototypeMocks,
	});
	const mockQuery = useQuery({
		queryKey: ["trading", "orders", params],
		queryFn: () => apiClient.get<GetOrdersResponse>(buildOrdersQuery(params)),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
