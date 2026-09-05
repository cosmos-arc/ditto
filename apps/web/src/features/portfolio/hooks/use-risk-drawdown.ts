import { useQuery } from "@tanstack/react-query";
import { shouldUsePrototypeMocks } from "../api/runtime";

export function useRiskDrawdown() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	return useQuery({
		queryKey: ["trading", "risk", "drawdown"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getRiskDrawdown }) => getRiskDrawdown()),
		enabled: usePrototypeMocks,
	});
}
