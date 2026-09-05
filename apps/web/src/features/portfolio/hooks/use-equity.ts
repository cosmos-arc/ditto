import { useQuery } from "@tanstack/react-query";
import { shouldUsePrototypeMocks } from "../api/runtime";

interface UseEquityOptions {
	readonly enabled?: boolean;
}

export function useEquity(options: UseEquityOptions = {}) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	return useQuery({
		queryKey: ["trading", "equity"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getEquity }) => getEquity()),
		enabled: usePrototypeMocks && (options.enabled ?? true),
	});
}
