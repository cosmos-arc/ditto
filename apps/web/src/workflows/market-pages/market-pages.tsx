import { useQuery } from "@tanstack/react-query";
import { fetchInstrumentCatalog, fetchInstrumentIdentity, type InstrumentCatalogFilter } from "@/features/instruments";
import {
	ASharesPage as ASharesView,
	CalendarPage as CalendarView,
	fetchCalendarStatus,
	type MarketCatalog,
	type MarketCatalogInstrument,
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
	// 名称/代码检索走 metadata 目录（分页拉取，UI 负责按 offset 续载）；
	// 每个已保存对象按精确身份经现有单对象解析重开。
	const searchCatalog = async (term: string, offset: number): Promise<MarketCatalog> => {
		const catalog = await fetchInstrumentCatalog({ search: term, limit: 20, offset });
		return { items: catalog.items.map(toMarketInstrument), total: catalog.total };
	};
	const resolveEntry = async (instrumentId: number): Promise<MarketCatalogInstrument> => {
		const instrument = await fetchInstrumentIdentity(String(instrumentId));
		return toMarketInstrument(instrument);
	};
	return <WatchlistView resolveEntry={resolveEntry} searchCatalog={searchCatalog} />;
}

function toMarketInstrument(instrument: {
	readonly asset_class: string;
	readonly exchange: string;
	readonly instrument_id: number;
	readonly is_active: boolean;
	readonly name: string;
	readonly ticker: string;
}): MarketCatalogInstrument {
	return {
		asset_class: instrument.asset_class,
		exchange: instrument.exchange,
		instrument_id: instrument.instrument_id,
		is_active: instrument.is_active,
		name: instrument.name,
		ticker: instrument.ticker,
	};
}

/** Cross-feature composition for ingestion-status-backed calendar data status. */
export function CalendarPage() {
	const status = useCalendarStatus();
	return <CalendarView status={status} />;
}
