import { useQuery } from "@tanstack/react-query";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useRecentSignals() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.recentSignals, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "signals", "recent"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getRecentSignals }) => getRecentSignals()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
