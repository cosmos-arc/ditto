import { useQuery } from "@tanstack/react-query";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function usePendingActions() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.pendingActions, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "pending-actions"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getPendingActions }) => getPendingActions()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
