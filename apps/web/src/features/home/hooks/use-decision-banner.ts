import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { DecisionBannerResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useDecisionBanner() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.decisionBanner, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "decision-banner"],
		queryFn: () => apiClient.get<DecisionBannerResponse>("/home/decision-banner"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
