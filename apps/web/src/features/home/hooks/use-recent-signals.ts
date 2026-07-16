import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRecentSignalsResponse } from "@/types";

export function useRecentSignals() {
	return useQuery({
		queryKey: ["home", "signals", "recent"],
		queryFn: () => apiClient.get<GetRecentSignalsResponse>("/home/signals/recent"),
	});
}
