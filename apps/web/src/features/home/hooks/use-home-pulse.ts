import { useQuery } from "@tanstack/react-query";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useHomePulse() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.pulse, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "pulse"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getHomePulse }) => getHomePulse()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
