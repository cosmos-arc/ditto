import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetPositionsResponse } from "@/types";

export function usePositions() {
	return useQuery({
		queryKey: ["trading", "positions"],
		queryFn: () => apiClient.get<GetPositionsResponse>("/trading/positions"),
	});
}
