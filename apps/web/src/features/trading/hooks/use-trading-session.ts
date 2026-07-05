import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { TradingSessionResponse } from "@/types";

interface UseTradingSessionOptions {
	readonly enabled?: boolean;
}

export function useTradingSession(options: UseTradingSessionOptions = {}) {
	return useQuery({
		queryKey: ["trading", "session"],
		queryFn: () => apiClient.get<TradingSessionResponse>("/trading/session"),
		enabled: options.enabled ?? true,
	});
}
