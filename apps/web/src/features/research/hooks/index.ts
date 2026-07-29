import { useQuery } from "@tanstack/react-query";
import { apiClient, withQueryParams } from "@/lib/api-client";
import type {
	GetFactorsResponse,
	GetResearchRunsResponse,
	GetReviewQueueResponse,
	PaginatedRequest,
	ResearchPulseResponse,
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
		queryFn: () => apiClient.get<GetFactorsResponse>(withQueryParams("/factors", params)),
	});
}

export function useResearchRuns() {
	return useQuery({
		queryKey: ["research", "runs"],
		queryFn: () => apiClient.get<GetResearchRunsResponse>("/research/runs"),
	});
}

export { useExperiments } from "./use-experiments";
export { useReviewPacket } from "./use-review-packet";
export { useReviews } from "./use-reviews";

export function useReviewQueue() {
	return useQuery({
		queryKey: ["research", "review-queue"],
		queryFn: () => apiClient.get<GetReviewQueueResponse>("/research/review-queue"),
	});
}

export { useFactorAnalysis, useFactorDetail } from "./use-factor-detail";
export { useRegimeCurrent } from "./use-regime-current";
export { useRegimeDrivers } from "./use-regime-drivers";
export { useRegimeHistory } from "./use-regime-history";
export { useRegimeStrategyImpact } from "./use-regime-strategy-impact";
