import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetScreenerPresetsResponse } from "@/types";

export function useScreenerPresets() {
	return useQuery({
		queryKey: ["screener", "presets"],
		queryFn: () => apiClient.get<GetScreenerPresetsResponse>("/screener/presets"),
	});
}
