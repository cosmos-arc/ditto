import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { DecisionBannerResponse } from "@/types";

export function useDecisionBanner() {
	return useQuery({
		queryKey: ["home", "decision-banner"],
		queryFn: () =>
			apiClient.get<DecisionBannerResponse>("/home/decision-banner"),
	});
}
