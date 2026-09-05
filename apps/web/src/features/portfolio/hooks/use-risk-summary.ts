import { useQuery } from "@tanstack/react-query";
import { shouldUsePrototypeMocks } from "../api/runtime";

export function useRiskSummary() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	return useQuery({
		queryKey: ["trading", "risk", "summary"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getRiskSummary }) => getRiskSummary()),
		enabled: usePrototypeMocks,
	});
}
