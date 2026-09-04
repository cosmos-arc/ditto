import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { GetPendingActionsResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function usePendingActions() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.pendingActions, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "pending-actions"],
		queryFn: () => apiClient.get<GetPendingActionsResponse>("/home/pending-actions"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
