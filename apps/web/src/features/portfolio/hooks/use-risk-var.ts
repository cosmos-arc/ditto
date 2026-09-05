import { useQuery } from "@tanstack/react-query";
import { shouldUsePrototypeMocks } from "../api/runtime";

export function useRiskVar() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	return useQuery({
		queryKey: ["trading", "risk", "var"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getRiskVar }) => getRiskVar()),
		enabled: usePrototypeMocks,
	});
}
