import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetHomeAgentFindingsResponse } from "@/types";

export function useAgentFindings() {
	return useQuery({
		queryKey: ["home", "agent-findings"],
		queryFn: () =>
			apiClient.get<GetHomeAgentFindingsResponse>("/home/agent-findings"),
	});
}
