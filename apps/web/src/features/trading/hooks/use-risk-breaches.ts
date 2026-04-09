import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRiskBreachesRequest, GetRiskBreachesResponse } from "@/types";

function buildBreachesQuery(params?: GetRiskBreachesRequest): string {
	if (!params) return "/trading/risk/breaches";

	const searchParams = new URLSearchParams();
	if (params.page) searchParams.set("page", String(params.page));
	if (params.pageSize) searchParams.set("pageSize", String(params.pageSize));

	const qs = searchParams.toString();
	return qs ? `/trading/risk/breaches?${qs}` : "/trading/risk/breaches";
}

export function useRiskBreaches(params?: GetRiskBreachesRequest) {
	return useQuery({
		queryKey: ["trading", "risk", "breaches", params],
		queryFn: () => apiClient.get<GetRiskBreachesResponse>(buildBreachesQuery(params)),
	});
}
