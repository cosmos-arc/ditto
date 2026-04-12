import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetMarketPulseMetricsResponse } from "@/types";

export function useMarketPulseMetrics() {
	return useQuery({
		queryKey: ["market", "pulse-metrics"],
		queryFn: () =>
			apiClient.get<GetMarketPulseMetricsResponse>("/home/pulse-metrics"),
	});
}
