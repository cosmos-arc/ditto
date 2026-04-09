import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type {
	ResearchPulseResponse,
	GetFactorsResponse,
	GetResearchRunsResponse,
	GetExperimentsResponse,
	GetReviewQueueResponse,
	PaginatedRequest,
} from "@/types";

export function useResearchPulse() {
	return useQuery({
		queryKey: ["research", "pulse"],
		queryFn: () => apiClient.get<ResearchPulseResponse>("/research/pulse"),
	});
}

export function useFactors(params?: PaginatedRequest) {
	return useQuery({
		queryKey: ["research", "factors", params],
		queryFn: () => apiClient.get<GetFactorsResponse>("/factors", params),
	});
}

export function useResearchRuns() {
	return useQuery({
		queryKey: ["research", "runs"],
		queryFn: () => apiClient.get<GetResearchRunsResponse>("/research/runs"),
	});
}

export function useExperiments() {
	return useQuery({
		queryKey: ["research", "experiments"],
		queryFn: () => apiClient.get<GetExperimentsResponse>("/research/experiments"),
	});
}

export function useReviewQueue() {
	return useQuery({
		queryKey: ["research", "review-queue"],
		queryFn: () => apiClient.get<GetReviewQueueResponse>("/research/review-queue"),
	});
}

export { useRegimeCurrent } from "./use-regime-current";
export { useRegimeDrivers } from "./use-regime-drivers";
export { useRegimeHistory } from "./use-regime-history";
export { useRegimeStrategyImpact } from "./use-regime-strategy-impact";
export { useFactorDetail, useFactorAnalysis } from "./use-factor-detail";
