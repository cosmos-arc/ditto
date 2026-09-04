import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetDataHealthResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useDataHealth() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.dataHealth, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "data-health"],
		queryFn: () => apiClient.get<GetDataHealthResponse>("/home/data-health"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
