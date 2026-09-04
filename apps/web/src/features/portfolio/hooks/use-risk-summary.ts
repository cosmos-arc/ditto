import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { RiskSummaryResponse } from "@/types";

export function useRiskSummary() {
	return useQuery({
		queryKey: ["trading", "risk", "summary"],
		queryFn: () => apiClient.get<RiskSummaryResponse>("/trading/risk/summary"),
	});
}
