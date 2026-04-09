import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRiskVarResponse } from "@/types";

export function useRiskVar() {
	return useQuery({
		queryKey: ["trading", "risk", "var"],
		queryFn: () => apiClient.get<GetRiskVarResponse>("/trading/risk/var"),
	});
}
