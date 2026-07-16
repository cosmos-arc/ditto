import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetDataHealthResponse } from "@/types";

export function useDataHealth() {
	return useQuery({
		queryKey: ["home", "data-health"],
		queryFn: () =>
			apiClient.get<GetDataHealthResponse>("/home/data-health"),
	});
}
