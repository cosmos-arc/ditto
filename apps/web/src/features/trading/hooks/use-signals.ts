import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalsRequest, GetSignalsResponse } from "@/types";

function buildSignalsQuery(params?: GetSignalsRequest): string {
	if (!params) return "/trading/signals";

	const searchParams = new URLSearchParams();
	if (params.tab) searchParams.set("tab", params.tab);
	if (params.page) searchParams.set("page", String(params.page));
	if (params.limit) searchParams.set("limit", String(params.limit));
	if (params.pageSize) searchParams.set("pageSize", String(params.pageSize));

	const qs = searchParams.toString();
	return qs ? `/trading/signals?${qs}` : "/trading/signals";
}

export function useSignals(params?: GetSignalsRequest) {
	return useQuery({
		queryKey: ["trading", "signals", params],
		queryFn: () => apiClient.get<GetSignalsResponse>(buildSignalsQuery(params)),
	});
}
