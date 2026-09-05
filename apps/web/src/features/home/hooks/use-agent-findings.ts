import { useQuery } from "@tanstack/react-query";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useAgentFindings() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.agentFindings, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "agent-findings"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getHomeAgentFindings }) => getHomeAgentFindings()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
