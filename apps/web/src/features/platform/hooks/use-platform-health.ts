import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { PlatformHealthResponse } from "@/types";

export function usePlatformHealth() {
	return useQuery({
		queryKey: ["platform", "health"],
		queryFn: () => apiClient.get<PlatformHealthResponse>("/platform/health"),
	});
}
