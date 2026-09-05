import { useQuery } from "@tanstack/react-query";
import { isMockRuntime } from "@/api";
import { type FactorDiagnosticsScope, fetchFactorDiagnostics, mapFactorDiagnostics } from "../api/factor-diagnostics";

export function useFactorDetail(id: string) {
	const usePrototypeMocks = isMockRuntime();
	return useQuery({
		queryKey: ["factors", id],
		queryFn: () => import("@/mocks/prototype-api").then(({ getFactorDetail }) => getFactorDetail(id)),
		enabled: usePrototypeMocks && id.length > 0,
	});
}

export function useFactorAnalysis(id: string) {
	const usePrototypeMocks = isMockRuntime();
	return useQuery({
		queryKey: ["factors", id, "analysis"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getFactorAnalysis }) => getFactorAnalysis(id)),
		enabled: usePrototypeMocks && id.length > 0,
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
