import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { TradingSessionResponse } from "@/types";

export function useTradingSession() {
	return useQuery({
		queryKey: ["trading", "session"],
		queryFn: () => apiClient.get<TradingSessionResponse>("/trading/session"),
	});
}
