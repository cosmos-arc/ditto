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

const POLLING_STATUSES = new Set(["queued", "running", "pausing", "cancelling", "resuming"]);

export function experimentPollingInterval(status: string | undefined): 2000 | false {
	return POLLING_STATUSES.has(status ?? "") ? 2000 : false;
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

export function useExperimentComparison(experimentId: string) {
	return useQuery({
		queryKey: experimentKeys.comparison(experimentId),
		queryFn: () => fetchExperimentComparison(experimentId),
	});
}

export function useExperimentArtifacts(experimentId: string) {
	return useQuery({
		queryKey: experimentKeys.artifacts(experimentId),
		queryFn: () => fetchExperimentArtifacts(experimentId),
	});
}

export function useExperimentSelectionEvidence(experimentId: string) {
	return useQuery({
		queryKey: experimentKeys.selectionEvidence(experimentId),
		queryFn: () => fetchExperimentSelectionEvidence(experimentId),
		retry: false,
	});
}
