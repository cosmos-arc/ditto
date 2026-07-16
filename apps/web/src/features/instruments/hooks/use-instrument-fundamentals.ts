import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetInstrumentFundamentalsResponse } from "@/types";

export function useInstrumentFundamentals(id: string) {
	return useQuery({
		queryKey: ["instruments", id, "fundamentals"],
		queryFn: () =>
			apiClient.get<GetInstrumentFundamentalsResponse>(`/instruments/${id}/fundamentals`),
		enabled: id.length > 0,
	});
}
