import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRiskExposureResponse } from "@/types";

export function useRiskExposure() {
	return useQuery({
		queryKey: ["trading", "risk", "exposure"],
		queryFn: () => apiClient.get<GetRiskExposureResponse>("/trading/risk/exposure"),
	});
}
