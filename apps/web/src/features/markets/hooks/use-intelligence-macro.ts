import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetIntelligenceMacroResponse } from "@/types";

export function useIntelligenceMacro() {
	return useQuery({
		queryKey: ["markets", "intelligence", "macro"],
		queryFn: () => apiClient.get<GetIntelligenceMacroResponse>("/markets/intelligence/macro"),
	});
}
