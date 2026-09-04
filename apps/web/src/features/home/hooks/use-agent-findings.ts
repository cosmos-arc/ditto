import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetHomeAgentFindingsResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useAgentFindings() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.agentFindings, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "agent-findings"],
		queryFn: () => apiClient.get<GetHomeAgentFindingsResponse>("/home/agent-findings"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
