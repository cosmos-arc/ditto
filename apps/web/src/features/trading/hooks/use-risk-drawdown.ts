import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRiskDrawdownResponse } from "@/types";

export function useRiskDrawdown() {
	return useQuery({
		queryKey: ["trading", "risk", "drawdown"],
		queryFn: () => apiClient.get<GetRiskDrawdownResponse>("/trading/risk/drawdown"),
	});
}
