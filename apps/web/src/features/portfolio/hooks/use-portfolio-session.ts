import { useQuery } from "@tanstack/react-query";
import { shouldUsePrototypeMocks } from "../api/runtime";

interface UsePortfolioSessionOptions {
	readonly enabled?: boolean;
}

export function usePortfolioSession(options: UsePortfolioSessionOptions = {}) {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	return useQuery({
		queryKey: ["trading", "session"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getPortfolioSession }) => getPortfolioSession()),
		enabled: usePrototypeMocks && (options.enabled ?? true),
	});
}
