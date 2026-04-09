import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetSignalDetailResponse } from "@/types";

export function useSignalDetail(id: string) {
	return useQuery({
		queryKey: ["trading", "signals", id],
		queryFn: () => apiClient.get<GetSignalDetailResponse>(`/trading/signals/${id}`),
	});
}
