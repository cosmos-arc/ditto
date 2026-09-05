import { useQuery } from "@tanstack/react-query";
import { isMockRuntime } from "@/api";
import type { PaginatedRequest } from "@/types";

export function useResearchPulse() {
	const usePrototypeMocks = isMockRuntime();
	return useQuery({
		queryKey: ["research", "pulse"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getResearchPulse }) => getResearchPulse()),
		enabled: usePrototypeMocks,
	});
}

export function useFactors(params?: PaginatedRequest) {
	const usePrototypeMocks = isMockRuntime();
	return useQuery({
		queryKey: ["research", "factors", params],
		queryFn: () => import("@/mocks/prototype-api").then(({ getFactors }) => getFactors(params)),
		enabled: usePrototypeMocks,
	});
}

export function useResearchRuns() {
	const usePrototypeMocks = isMockRuntime();
	return useQuery({
		queryKey: ["research", "runs"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getResearchRuns }) => getResearchRuns()),
		enabled: usePrototypeMocks,
	});
}

export { useCandidateEvidence } from "./use-candidate-evidence";
export { useCandidateSelection } from "./use-candidate-selection";
export {
	useExperiment,
	useExperimentArtifacts,
	useExperimentCandidates,
	useExperimentComparison,
	useExperimentGates,
	useExperimentSelectionEvidence,
} from "./use-experiment";
export { useExperimentLaunch } from "./use-experiment-launch";
export { useExperimentControl, useExperimentRetryFold } from "./use-experiment-mutations";
export { useExperimentPreflight } from "./use-experiment-preflight";
export { useExperiments } from "./use-experiments";
export { useHoldoutEvaluation } from "./use-holdout-evaluation";
export { useReviewPacket } from "./use-review-packet";
export { useReviews } from "./use-reviews";

export function useReviewQueue() {
	const usePrototypeMocks = isMockRuntime();
	return useQuery({
		queryKey: ["research", "review-queue"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getReviewQueue }) => getReviewQueue()),
		enabled: usePrototypeMocks,
	});
}

export { useFactorCatalog } from "./use-factor-catalog";
export { useFactorAnalysis, useFactorDetail, useFactorDiagnostics } from "./use-factor-detail";
export { isCompleteRegimeScope, regimeDiagnosticsKeys, useRegimeDiagnostics } from "./use-regime-diagnostics";
export { universeKeys, useUniverseCommands, useUniverseMembers, useUniverses } from "./use-universes";
