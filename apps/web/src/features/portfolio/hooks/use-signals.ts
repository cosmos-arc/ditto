import { useQuery } from "@tanstack/react-query";
import type { GetSignalsRequest } from "@/types";
import { mapDailyDecisionToSignalsResponse, mapDailyDecisionV2ToLegacy } from "../api/mappers";
import { DEFAULT_STRATEGY_ID, tradingKeys } from "../api/query-keys";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function useSignals(params?: GetSignalsRequest) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(
		undefined,
		(report) => mapDailyDecisionToSignalsResponse(mapDailyDecisionV2ToLegacy(report), params),
		{ enabled: !usePrototypeMocks },
	);
	const mockQuery = useQuery({
		queryKey: tradingKeys.signals(DEFAULT_STRATEGY_ID, params?.tab),
		queryFn: () => import("@/mocks/prototype-api").then(({ getSignals }) => getSignals(params)),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
