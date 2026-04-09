import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetPipelinesResponse, PaginatedRequest } from "@/types";

export function usePipelines(params?: PaginatedRequest) {
	return useQuery({
		queryKey: ["platform", "pipelines", params],
		queryFn: () =>
			apiClient.get<GetPipelinesResponse>("/platform/pipelines", {
				...params,
			}),
	});
}
