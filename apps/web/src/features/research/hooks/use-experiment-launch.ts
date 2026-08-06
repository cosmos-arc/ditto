import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
	type ExperimentLaunchReceipt,
	type ExperimentPlanningRequest,
	launchExperiment,
	mapExperimentLaunchReceipt,
} from "../api/experiments";
import { experimentKeys } from "../api/query-keys";

type LaunchVariables = {
	readonly planning: ExperimentPlanningRequest;
	readonly confirmedPlanHash: string;
	readonly idempotencyKey: string;
};

export function useExperimentLaunch() {
	const queryClient = useQueryClient();
	return useMutation<ExperimentLaunchReceipt, Error, LaunchVariables>({
		mutationFn: ({ planning, confirmedPlanHash, idempotencyKey }) =>
			launchExperiment(planning, confirmedPlanHash, idempotencyKey).then(mapExperimentLaunchReceipt),
		onSuccess: async (receipt) => {
			await Promise.all([
				queryClient.invalidateQueries({ queryKey: experimentKeys.list() }),
				queryClient.invalidateQueries({ queryKey: experimentKeys.detail(receipt.experimentId) }),
			]);
		},
	});
}
