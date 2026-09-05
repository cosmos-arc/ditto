import { useQuery } from "@tanstack/react-query";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useHomeAlerts() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.alerts, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "alerts"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getHomeAlerts }) => getHomeAlerts()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
