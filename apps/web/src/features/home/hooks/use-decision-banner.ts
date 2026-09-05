import { useQuery } from "@tanstack/react-query";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useDecisionBanner() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.decisionBanner, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "decision-banner"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getDecisionBanner }) => getDecisionBanner()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
