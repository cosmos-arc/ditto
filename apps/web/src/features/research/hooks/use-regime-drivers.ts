import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetRegimeDriversResponse } from "@/types";

export function useRegimeDrivers() {
	return useQuery({
		queryKey: ["research", "regime", "drivers"],
		queryFn: () => apiClient.get<GetRegimeDriversResponse>("/research/regime/drivers"),
	});
}
