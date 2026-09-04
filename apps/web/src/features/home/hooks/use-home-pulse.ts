import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { HomePulseResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useHomePulse() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.pulse, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "pulse"],
		queryFn: () => apiClient.get<HomePulseResponse>("/home/pulse"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
