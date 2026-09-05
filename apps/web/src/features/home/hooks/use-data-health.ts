import { useQuery } from "@tanstack/react-query";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useDataHealth() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection((projection) => projection.dataHealth, { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["home", "data-health"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getDataHealth }) => getDataHealth()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
