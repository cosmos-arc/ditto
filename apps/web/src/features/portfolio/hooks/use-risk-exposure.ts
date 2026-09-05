import { useQuery } from "@tanstack/react-query";
import { shouldUsePrototypeMocks } from "../api/runtime";

export function useRiskExposure() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	return useQuery({
		queryKey: ["trading", "risk", "exposure"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getRiskExposure }) => getRiskExposure()),
		enabled: usePrototypeMocks,
	});
}
