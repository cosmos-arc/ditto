import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetEquityResponse } from "@/types";

export function useEquity() {
	return useQuery({
		queryKey: ["trading", "equity"],
		queryFn: () => apiClient.get<GetEquityResponse>("/trading/equity"),
	});
}
