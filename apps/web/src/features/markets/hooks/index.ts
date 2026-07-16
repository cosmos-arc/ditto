import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type {
	MarketContextResponse,
	ScopeStripResponse,
	GetMarketOverviewResponse,
	GetCrossMatrixResponse,
	GetMacroDriversResponse,
	GetCapitalRotationResponse,
} from "@/types";

export function useMarketContext() {
	return useQuery({
		queryKey: ["markets", "context"],
		queryFn: () => apiClient.get<MarketContextResponse>("/markets/context"),
	});
}

export function useScopeStrip() {
	return useQuery({
		queryKey: ["markets", "scope-strip"],
		queryFn: () => apiClient.get<ScopeStripResponse>("/markets/scope-strip"),
	});
}

export function useMarketOverview() {
	return useQuery({
		queryKey: ["markets", "overview"],
		queryFn: () => apiClient.get<GetMarketOverviewResponse>("/markets/overview"),
	});
}

export function useCrossMatrix() {
	return useQuery({
		queryKey: ["markets", "cross-matrix"],
		queryFn: () => apiClient.get<GetCrossMatrixResponse>("/markets/cross-matrix"),
	});
}

export function useMacroDrivers() {
	return useQuery({
		queryKey: ["markets", "macro-drivers"],
		queryFn: () => apiClient.get<GetMacroDriversResponse>("/markets/macro-drivers"),
	});
}

export function useCapitalRotation() {
	return useQuery({
		queryKey: ["markets", "capital-rotation"],
		queryFn: () => apiClient.get<GetCapitalRotationResponse>("/markets/capital-rotation"),
	});
}

export { useIntelligenceFlow } from "./use-intelligence-flow";
export { useIntelligenceMacro } from "./use-intelligence-macro";
export { useIntelligenceFundamentals } from "./use-intelligence-fundamentals";
export { useAShares } from "./use-a-shares";
export { useMarketCalendar } from "./use-market-calendar";
