import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetInstrumentResponse } from "@/types";

export function useInstrumentDetail(id: string) {
	return useQuery({
		queryKey: ["instruments", id],
		queryFn: () => apiClient.get<GetInstrumentResponse>(`/instruments/${id}`),
		enabled: id.length > 0,
	});
}
