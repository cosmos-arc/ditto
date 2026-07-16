import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { HomePulseResponse } from "@/types";

export function useHomePulse() {
	return useQuery({
		queryKey: ["home", "pulse"],
		queryFn: () => apiClient.get<HomePulseResponse>("/home/pulse"),
	});
}
