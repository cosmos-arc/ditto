import { useQuery } from "@tanstack/react-query";
import type { GetOrdersRequest } from "@/types";
import { mapDailyDecisionV2ToOrdersResponse } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function useOrders(params?: GetOrdersRequest) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(undefined, (report) => mapDailyDecisionV2ToOrdersResponse(report, params), {
		enabled: !usePrototypeMocks,
	});
	const mockQuery = useQuery({
		queryKey: ["trading", "orders", params],
		queryFn: () => import("@/mocks/prototype-api").then(({ getOrders }) => getOrders(params)),
		enabled: usePrototypeMocks,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
