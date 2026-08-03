import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
	type CandidateSelectionReceiptResponse,
	type CandidateSelectionRequest,
	selectExperimentCandidate,
} from "../api/experiments";
import { experimentKeys } from "../api/query-keys";

type Variables = {
	readonly experimentId: string;
	readonly request: CandidateSelectionRequest;
	readonly idempotencyKey: string;
};

export function useCandidateSelection() {
	const queryClient = useQueryClient();
	return useMutation<CandidateSelectionReceiptResponse, Error, Variables>({
		mutationFn: ({ experimentId, request, idempotencyKey }) =>
			selectExperimentCandidate(experimentId, request, idempotencyKey),
		onSuccess: (receipt) => {
			void Promise.all([
				queryClient.invalidateQueries({ queryKey: experimentKeys.detail(receipt.experiment_id) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.list() }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.candidates(receipt.experiment_id) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.gates(receipt.experiment_id) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.comparison(receipt.experiment_id) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.artifacts(receipt.experiment_id) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.selectionEvidence(receipt.experiment_id) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.candidateEvidenceRoot(receipt.experiment_id) }),
			]);
		},
	});
}
