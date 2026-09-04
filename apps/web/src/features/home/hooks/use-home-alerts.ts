import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetHomeAlertsResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useHomeAlerts() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.alerts, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "alerts"],
		queryFn: () => apiClient.get<GetHomeAlertsResponse>("/home/alerts"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
