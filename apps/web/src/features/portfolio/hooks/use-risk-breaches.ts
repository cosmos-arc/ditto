import { useQuery } from "@tanstack/react-query";
import type { GetRiskBreachesRequest } from "@/types";
import { shouldUsePrototypeMocks } from "../api/runtime";

export function useRiskBreaches(params?: GetRiskBreachesRequest) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	return useQuery({
		queryKey: ["trading", "risk", "breaches", params],
		queryFn: () => import("@/mocks/prototype-api").then(({ getRiskBreaches }) => getRiskBreaches(params)),
		enabled: usePrototypeMocks,
	});
}
