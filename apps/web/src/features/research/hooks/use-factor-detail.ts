import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { FactorAnalysisResponse, FactorDetailResponse } from "@/types";
import { type FactorDiagnosticsScope, fetchFactorDiagnostics, mapFactorDiagnostics } from "../api/factor-diagnostics";

export function useFactorDetail(id: string) {
	return useQuery({
		queryKey: ["factors", id],
		queryFn: () => apiClient.get<FactorDetailResponse>(`/factors/${id}`),
	});
}

export function useFactorAnalysis(id: string) {
	return useQuery({
		queryKey: ["factors", id, "analysis"],
		queryFn: () => apiClient.get<FactorAnalysisResponse>(`/factors/${id}/analysis`),
	});
}

/** 完整 scope 缺一不可；不会回退 prototype factor analysis。 */
export function useFactorDiagnostics(id: string, scope: FactorDiagnosticsScope | null) {
	return useQuery({
		queryKey: [
			"research",
			"factor-diagnostics",
			id,
			scope?.snapshotId ?? "missing",
			scope?.startDate ?? "missing",
			scope?.endDate ?? "missing",
			scope?.registryHash ?? "missing",
		],
		queryFn: () => fetchFactorDiagnostics(id, scope as FactorDiagnosticsScope).then(mapFactorDiagnostics),
		enabled: Boolean(id && scope),
	});
}
