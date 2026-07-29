import { useQuery } from "@tanstack/react-query";
import type { ExperimentListItem } from "@/types";
import { fetchExperiments, mapExperimentListItem } from "../api/experiments";

/** 列出实验（`GET /v1/research/experiments`），返回 view-model。 */
export function useExperiments() {
	return useQuery({
		queryKey: ["research", "experiments", "list"],
		queryFn: async () => (await fetchExperiments()).map(mapExperimentListItem),
	});
}

export type { ExperimentListItem };
