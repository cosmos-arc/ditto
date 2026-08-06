import { useMutation } from "@tanstack/react-query";
import {
	type ExperimentPlanningRequest,
	type ExperimentPreflight,
	mapExperimentPreflight,
	preflightExperiment,
} from "../api/experiments";

/** Read-only planning gate. The server response is the sole budget and eligibility truth. */
export function useExperimentPreflight() {
	return useMutation<ExperimentPreflight, Error, ExperimentPlanningRequest>({
		mutationFn: (planning) => preflightExperiment(planning).then(mapExperimentPreflight),
	});
}
