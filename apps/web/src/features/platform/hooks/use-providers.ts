import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetProvidersResponse } from "@/types";

export function useProviders() {
	return useQuery({
		queryKey: ["platform", "providers"],
		queryFn: () => apiClient.get<GetProvidersResponse>("/platform/providers"),
	});
}
