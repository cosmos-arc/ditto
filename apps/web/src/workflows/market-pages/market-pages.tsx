import { useQuery } from "@tanstack/react-query";
import {
	fetchInstrumentBars,
	fetchInstrumentCatalog,
	fetchInstrumentIdentity,
	type InstrumentCatalogFilter,
} from "@/features/instruments";
import {
	ASharesPage as ASharesView,
	CalendarPage as CalendarView,
	fetchCalendarStatus,
	type MarketCatalog,
	type MarketCatalogInstrument,
	type MarketQuoteSnapshot,
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

/** 上海交易所时区的"今天"（盘后观察以交易所日界为准，非 UTC 日）。 */
function shanghaiToday(): string {
	return new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

function dateDaysBefore(date: string, days: number): string {
	const parsed = new Date(`${date}T00:00:00Z`);
	parsed.setUTCDate(parsed.getUTCDate() - days);
	return parsed.toISOString().slice(0, 10);
}

/** 行情观察窗口：锚点日前推 45 个自然日，足以覆盖前后两根日 K 的涨跌口径。 */
const QUOTE_WINDOW_DAYS = 45;

/** Cross-feature composition for the top-level Markets overview. */
export function MarketsPage() {
	const catalogQuery = useMarketCatalog({ limit: 100 });
	const contextQuery = useCurrentMarketContext();
	// 盘后落地锚点：最近完整交易日来自 calendar 数据集真实摄取结果。
	const calendarQuery = useCalendarStatus();
	return (
		<MarketsView
			calendarQuery={calendarQuery}
			catalogQuery={catalogQuery}
			contextQuery={contextQuery}
			etfCandidates={<ETFCandidates />}
		/>
	);
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
	// 最近完整交易日锚点来自 calendar 数据集真实摄取结果。日历状态落定前
	// 不发起行情请求（用今天当窗口会撞上日历权威 fail closed）；日历不可得
	// 时回退到上海今天（服务端仍按日历权威钳制），摘要如实显示"未解析"。
	const observationQuery = useCalendarStatus();
	const anchorDate =
		observationQuery.data?.latest_status === "success" && observationQuery.data.latest_date
			? observationQuery.data.latest_date
			: observationQuery.isLoading
				? null
				: shanghaiToday();
	// 行情列复用既有日 K 合同：窗口内最后一根收盘与对前一根涨跌，
	// 与标的图表 Primary Answer 同口径（表图数字对齐）。
	const resolveQuote = async (instrumentId: number, end: string): Promise<MarketQuoteSnapshot | null> => {
		const chart = await fetchInstrumentBars(String(instrumentId), {
			adjustment: "none",
			allowExperimental: false,
			endDate: end,
			period: "daily",
			startDate: dateDaysBefore(end, QUOTE_WINDOW_DAYS),
		});
		const last = chart.bars.at(-1);
		if (!last) return null;
		const previous = chart.bars.at(-2);
		const change = previous ? last.close - previous.close : null;
		const changePercent = change !== null && previous ? (change / previous.close) * 100 : null;
		return { change, changePercent, close: last.close, tradeDate: last.trade_date };
	};
	return (
		<WatchlistView
			observationQuery={observationQuery}
			quote={{ anchorDate, resolve: resolveQuote }}
			resolveEntry={resolveEntry}
			searchCatalog={searchCatalog}
		/>
	);
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
