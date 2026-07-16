import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRegimeCurrentResponse } from "@/types";

export function useRegimeCurrent() {
	return useQuery({
		queryKey: ["research", "regime", "current"],
		queryFn: () => apiClient.get<GetRegimeCurrentResponse>("/research/regime/current"),
	});
}
