import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetHomeAlertsResponse } from "@/types";

export function useHomeAlerts() {
	return useQuery({
		queryKey: ["home", "alerts"],
		queryFn: () => apiClient.get<GetHomeAlertsResponse>("/home/alerts"),
	});
}
