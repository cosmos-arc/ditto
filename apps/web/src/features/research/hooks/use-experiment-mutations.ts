import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
	controlExperiment,
	type ExperimentControlAction,
	type ExperimentControlReceiptResponse,
	retryExperimentFold,
} from "../api/experiments";
import { experimentKeys } from "../api/query-keys";

type ControlVariables = {
	readonly experimentId: string;
	readonly action: ExperimentControlAction;
	readonly expectedRevision: number;
	readonly idempotencyKey: string;
};

type RetryFoldVariables = {
	readonly experimentId: string;
	readonly candidateId: string;
	readonly foldId: string;
	readonly expectedRevision: number;
	readonly idempotencyKey: string;
};

async function invalidateExperiment(
	queryClient: ReturnType<typeof useQueryClient>,
	experimentId: string,
): Promise<void> {
	await Promise.all([
		queryClient.invalidateQueries({ queryKey: experimentKeys.detail(experimentId) }),
		queryClient.invalidateQueries({ queryKey: experimentKeys.list() }),
		queryClient.invalidateQueries({ queryKey: experimentKeys.candidates(experimentId) }),
		queryClient.invalidateQueries({ queryKey: experimentKeys.gates(experimentId) }),
		queryClient.invalidateQueries({ queryKey: experimentKeys.comparison(experimentId) }),
		queryClient.invalidateQueries({ queryKey: experimentKeys.artifacts(experimentId) }),
		queryClient.invalidateQueries({ queryKey: experimentKeys.selectionEvidence(experimentId) }),
		queryClient.invalidateQueries({ queryKey: experimentKeys.candidateEvidenceRoot(experimentId) }),
	]);
}

export function useExperimentControl() {
	const queryClient = useQueryClient();
	return useMutation<ExperimentControlReceiptResponse, Error, ControlVariables>({
		mutationFn: ({ experimentId, action, expectedRevision, idempotencyKey }) =>
			controlExperiment(experimentId, action, expectedRevision, idempotencyKey),
		onSuccess: (receipt) => invalidateExperiment(queryClient, receipt.experiment_id),
	});
}

export function useExperimentRetryFold() {
	const queryClient = useQueryClient();
	return useMutation<ExperimentControlReceiptResponse, Error, RetryFoldVariables>({
		mutationFn: ({ experimentId, candidateId, foldId, expectedRevision, idempotencyKey }) =>
			retryExperimentFold(
				experimentId,
				{ candidate_id: candidateId, fold_id: foldId, expected_revision: expectedRevision },
				idempotencyKey,
			),
		onSuccess: (receipt) => invalidateExperiment(queryClient, receipt.experiment_id),
	});
}
