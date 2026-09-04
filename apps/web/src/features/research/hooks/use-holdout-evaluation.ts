import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
	evaluateExperimentHoldout,
	type HoldoutEvaluationReceiptResponse,
	type HoldoutEvaluationRequest,
} from "../api/experiments";
import { experimentKeys } from "../api/query-keys";

type Variables = {
	readonly experimentId: string;
	readonly request: HoldoutEvaluationRequest;
	readonly idempotencyKey: string;
};

export function useHoldoutEvaluation() {
	const queryClient = useQueryClient();
	return useMutation<HoldoutEvaluationReceiptResponse, Error, Variables>({
		mutationFn: ({ experimentId, request, idempotencyKey }) =>
			evaluateExperimentHoldout(experimentId, request, idempotencyKey),
		onSettled: (_data, _error, variables) => {
			void Promise.all([
				queryClient.invalidateQueries({ queryKey: experimentKeys.detail(variables.experimentId) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.selectionEvidence(variables.experimentId) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.artifacts(variables.experimentId) }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.candidateEvidenceRoot(variables.experimentId) }),
			]);
		},
	});
}
