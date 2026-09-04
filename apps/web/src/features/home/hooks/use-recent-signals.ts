import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRecentSignalsResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useRecentSignals() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.recentSignals, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "signals", "recent"],
		queryFn: () => apiClient.get<GetRecentSignalsResponse>("/home/signals/recent"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
