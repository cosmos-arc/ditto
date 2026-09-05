import { useQuery } from "@tanstack/react-query";
import { mapDailyDecisionV2ToOrderDetail } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "./use-daily-decision-v2";

export function useOrderDetail(id: string) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const liveQuery = useDailyDecisionV2(undefined, (report) => mapDailyDecisionV2ToOrderDetail(report, id), {
		enabled: !usePrototypeMocks && id.length > 0,
	});
	const mockQuery = useQuery({
		queryKey: ["trading", "orders", id],
		queryFn: () => import("@/mocks/prototype-api").then(({ getOrderDetail }) => getOrderDetail(id)),
		enabled: usePrototypeMocks && id.length > 0,
	});

	return usePrototypeMocks ? mockQuery : liveQuery;
}
