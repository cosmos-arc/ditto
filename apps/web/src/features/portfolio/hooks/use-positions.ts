import { useQuery } from "@tanstack/react-query";
import { mapDailyDecisionV2ToLegacy, mapPositionsResponse } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function usePositions() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(
		undefined,
		(report) => mapPositionsResponse(mapDailyDecisionV2ToLegacy(report)),
		{
			enabled: !usePrototypeMocks,
		},
	);
	const mockQuery = useQuery({
		queryKey: ["trading", "positions"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getPositions }) => getPositions()),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
