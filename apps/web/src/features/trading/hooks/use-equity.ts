import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetEquityResponse } from "@/types";

interface UseEquityOptions {
	readonly enabled?: boolean;
}

export function useEquity(options: UseEquityOptions = {}) {
	return useQuery({
		queryKey: ["trading", "equity"],
		queryFn: () => apiClient.get<GetEquityResponse>("/trading/equity"),
		enabled: options.enabled ?? true,
	});
}
