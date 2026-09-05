import { useQuery } from "@tanstack/react-query";
import type { GetMarketIndicesResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";
import { useHomeLiveProjection } from "./use-home-live-projection";

export function useMarketIndices() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useHomeLiveProjection<GetMarketIndicesResponse>(() => ({ indices: [] }), { enabled: !useMocks });
	const mockQuery = useQuery({
		queryKey: ["market", "indices"],
		queryFn: () => import("@/mocks/prototype-api").then(({ getMarketIndices }) => getMarketIndices()),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
