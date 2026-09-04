import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { PortfolioSessionResponse } from "@/types";

interface UsePortfolioSessionOptions {
	readonly enabled?: boolean;
}

export function usePortfolioSession(options: UsePortfolioSessionOptions = {}) {
	return useQuery({
		queryKey: ["trading", "session"],
		queryFn: () => apiClient.get<PortfolioSessionResponse>("/trading/session"),
		enabled: options.enabled ?? true,
	});
}
