import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetMarketIndicesResponse } from "@/types";

export function useMarketIndices() {
	return useQuery({
		queryKey: ["market", "indices"],
		queryFn: () =>
			apiClient.get<GetMarketIndicesResponse>("/market/indices"),
	});
}
