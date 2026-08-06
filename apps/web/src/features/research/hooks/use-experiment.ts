import { useQuery } from "@tanstack/react-query";
import {
	fetchExperiment,
	fetchExperimentArtifacts,
	fetchExperimentCandidates,
	fetchExperimentComparison,
	fetchExperimentGates,
	fetchExperimentSelectionEvidence,
} from "../api/experiments";
import { experimentKeys } from "../api/query-keys";

const POLLING_STATUSES = new Set([
	"queued",
	"running",
	"pause_requested",
	"cancel_requested",
	"pausing",
	"cancelling",
	"resuming",
]);
const SELECTION_EVIDENCE_STAGES = new Set(["candidate_selection", "holdout", "evidence", "finalized"]);

export function experimentPollingInterval(status: string | undefined): 2000 | false {
	return POLLING_STATUSES.has(status ?? "") ? 2000 : false;
}

export function selectionEvidencePollingInterval(stage: string | undefined, hasData: boolean): 2000 | false {
	return SELECTION_EVIDENCE_STAGES.has(stage ?? "") && !hasData ? 2000 : false;
}

export function comparisonEvidencePollingInterval(
	stage: string | undefined,
	actualRevision: number | undefined,
	expectedRevision: number | undefined,
): 2000 | false {
	return SELECTION_EVIDENCE_STAGES.has(stage ?? "") && actualRevision !== expectedRevision ? 2000 : false;
}

export function useExperiment(experimentId: string) {
	return useQuery({
		queryKey: experimentKeys.detail(experimentId),
		queryFn: () => fetchExperiment(experimentId),
		refetchInterval: (query) => experimentPollingInterval(query.state.data?.status),
	});
}

export function useExperimentCandidates(experimentId: string) {
	return useQuery({
		queryKey: experimentKeys.candidates(experimentId),
		queryFn: () => fetchExperimentCandidates(experimentId),
	});
}

export function useExperimentGates(experimentId: string) {
	return useQuery({ queryKey: experimentKeys.gates(experimentId), queryFn: () => fetchExperimentGates(experimentId) });
}

export function useExperimentComparison(experimentId: string, stage: string | undefined, revision: number | undefined) {
	return useQuery({
		queryKey: experimentKeys.comparison(experimentId),
		queryFn: () => fetchExperimentComparison(experimentId),
		enabled: SELECTION_EVIDENCE_STAGES.has(stage ?? ""),
		retry: false,
		refetchInterval: (query) => comparisonEvidencePollingInterval(stage, query.state.data?.revision, revision),
	});
}

export function useExperimentArtifacts(experimentId: string) {
	return useQuery({
		queryKey: experimentKeys.artifacts(experimentId),
		queryFn: () => fetchExperimentArtifacts(experimentId),
	});
}

export function useExperimentSelectionEvidence(experimentId: string, stage: string | undefined) {
	return useQuery({
		queryKey: experimentKeys.selectionEvidence(experimentId),
		queryFn: () => fetchExperimentSelectionEvidence(experimentId),
		enabled: SELECTION_EVIDENCE_STAGES.has(stage ?? ""),
		retry: false,
		refetchInterval: (query) => selectionEvidencePollingInterval(stage, query.state.data !== undefined),
	});
}
