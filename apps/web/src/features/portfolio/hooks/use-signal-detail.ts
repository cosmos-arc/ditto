import { useQuery } from "@tanstack/react-query";
import { mapDailyDecisionToSignalDetail, mapDailyDecisionV2ToLegacy } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function useSignalDetail(id: string) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(
		undefined,
		(report) => mapDailyDecisionToSignalDetail(mapDailyDecisionV2ToLegacy(report), id),
		{ enabled: !usePrototypeMocks },
	);
	const mockQuery = useQuery({
		queryKey: ["trading", "signals", id],
		queryFn: () => import("@/mocks/prototype-api").then(({ getSignalDetail }) => getSignalDetail(id)),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
