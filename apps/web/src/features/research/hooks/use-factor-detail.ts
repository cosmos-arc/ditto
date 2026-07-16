import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type {
	FactorDetailResponse,
	FactorAnalysisResponse,
} from "@/types";

export function useFactorDetail(id: string) {
	return useQuery({
		queryKey: ["factors", id],
		queryFn: () =>
			apiClient.get<FactorDetailResponse>(`/factors/${id}`),
	});
}

export function useFactorAnalysis(id: string) {
	return useQuery({
		queryKey: ["factors", id, "analysis"],
		queryFn: () =>
			apiClient.get<FactorAnalysisResponse>(`/factors/${id}/analysis`),
	});
}
