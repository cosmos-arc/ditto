import { useQuery } from "@tanstack/react-query";
import { isMockRuntime } from "@/api/runtime-config";
import { type FactorDiagnosticsScope, fetchFactorDiagnostics, mapFactorDiagnostics } from "../api/factor-diagnostics";
import { type FactorSeriesRequest, fetchFactorEvaluationSeries } from "../api/factor-series";

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

/** 查询时计算的因子评估逐日序列；窗口绑定后启用（研究语义，生产环境后端 fail closed）。 */
export function useFactorEvaluationSeries(id: string, request: FactorSeriesRequest | null) {
	return useQuery({
		queryKey: [
			"research",
			"factor-evaluation-series",
			id,
			request?.startDate ?? "missing",
			request?.endDate ?? "missing",
			request?.holdingPeriod ?? 5,
			request?.nQuantiles ?? 5,
			request?.rollingIrWindow ?? 20,
			request?.assetClass ?? "etf",
			request?.adj ?? "none",
			request?.version ?? "auto",
		],
		queryFn: () => fetchFactorEvaluationSeries(id, request as FactorSeriesRequest),
		enabled: Boolean(id && request),
	});
}
