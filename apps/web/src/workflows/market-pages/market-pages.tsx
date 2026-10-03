import { useQuery } from "@tanstack/react-query";
import { fetchInstrumentCatalog, type InstrumentCatalogFilter } from "@/features/instruments";
import {
	ASharesPage as ASharesView,
	CalendarPage as CalendarView,
	fetchCalendarStatus,
	MarketsPage as MarketsView,
	WatchlistPage as WatchlistView,
} from "@/features/markets";
import { useCurrentMarketContext } from "@/workflows/market-context";
import { ETFCandidates } from "./etf-candidates";

const marketCatalogKeys = {
	all: ["market-page-catalog"] as const,
	list: (filter: InstrumentCatalogFilter) => [...marketCatalogKeys.all, filter] as const,
};

function useMarketCatalog(filter: InstrumentCatalogFilter = {}) {
	return useQuery({
		queryKey: marketCatalogKeys.list(filter),
		queryFn: () => fetchInstrumentCatalog(filter),
		staleTime: 60_000,
	});
}

function useCalendarStatus() {
	return useQuery({
		queryKey: ["market-page-calendar-status"],
		queryFn: () => fetchCalendarStatus(),
		staleTime: 60_000,
	});
}

/** Cross-feature composition for the top-level Markets overview. */
export function MarketsPage() {
	const catalogQuery = useMarketCatalog({ limit: 100 });
	const contextQuery = useCurrentMarketContext();
	return <MarketsView catalogQuery={catalogQuery} contextQuery={contextQuery} etfCandidates={<ETFCandidates />} />;
}

/** Cross-feature composition for the A-share identity catalog. */
export function ASharesPage() {
	const catalog = useMarketCatalog({ assetClass: "stock", isActive: true, limit: 100 });
	return <ASharesView catalog={catalog} />;
}

/** Cross-feature composition for the browser-local watchlist. */
export function WatchlistPage() {
	const catalog = useMarketCatalog({ limit: 100 });
	return <WatchlistView catalog={catalog} />;
}

/** Cross-feature composition for ingestion-status-backed calendar data status. */
export function CalendarPage() {
	const status = useCalendarStatus();
	return <CalendarView status={status} />;
}
