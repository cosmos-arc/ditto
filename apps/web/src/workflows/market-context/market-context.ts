import { useQuery } from "@tanstack/react-query";
import { fetchMarketContext, type MarketContext } from "@/features/markets";

export const currentMarketContextKeys = {
	all: ["market-evidence", "context"] as const,
	current: (asOf?: string) => [...currentMarketContextKeys.all, asOf ?? "current"] as const,
};

/**
 * Bind the market-context scope with PIT cutoffs, letting the server resolve the
 * observed source-snapshot set. Cross-feature orchestration belongs here, above
 * the markets capability, so pages do not own the adapter.
 */
export async function fetchCurrentMarketContext(asOf = new Date().toISOString()): Promise<MarketContext> {
	// 空快照集合法：服务端解析 observed 快照集。
	return fetchMarketContext({
		asOf,
		knowledgeCutoff: asOf,
		publicationCutoff: asOf,
		sourceSnapshotIds: [],
	});
}

export function useCurrentMarketContext(asOf?: string) {
	return useQuery({
		queryKey: currentMarketContextKeys.current(asOf),
		queryFn: () => fetchCurrentMarketContext(asOf),
		staleTime: 60_000,
	});
}
