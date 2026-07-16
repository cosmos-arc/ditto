import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetScreenerColumnsResponse } from "@/types";

export function useScreenerColumns() {
	return useQuery({
		queryKey: ["screener", "columns"],
		queryFn: () => apiClient.get<GetScreenerColumnsResponse>("/screener/columns"),
	});
}
