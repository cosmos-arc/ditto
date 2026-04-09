import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetIntelligenceFundamentalsResponse } from "@/types";

export function useIntelligenceFundamentals() {
	return useQuery({
		queryKey: ["markets", "intelligence", "fundamentals"],
		queryFn: () =>
			apiClient.get<GetIntelligenceFundamentalsResponse>("/markets/intelligence/fundamentals"),
	});
}
