import { useQuery } from "@tanstack/react-query";
import { apiClient, withQueryParams } from "@/lib/api-client";
import type {
	GetFactorLibraryResponse,
	PaginatedRequest,
} from "@/types";

export function useFactorLibrary(params?: PaginatedRequest) {
	return useQuery({
		queryKey: ["factor-library", params],
		queryFn: () =>
			apiClient.get<GetFactorLibraryResponse>(
				withQueryParams("/factor-library", params),
			),
	});
}
