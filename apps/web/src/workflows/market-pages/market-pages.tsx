import { useQuery } from "@tanstack/react-query";
import {
	fetchInstrumentBars,
	fetchInstrumentCatalog,
	fetchInstrumentIdentity,
	type InstrumentCatalogFilter,
	type InstrumentChart,
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
import { dateYearsBefore } from "@/lib/iso-calendar-date";
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

function dateDaysBefore(date: string, days: number): string {
	const parsed = new Date(`${date}T00:00:00Z`);
	parsed.setUTCDate(parsed.getUTCDate() - days);
	return parsed.toISOString().slice(0, 10);
}

/** 行情观察窄窗：锚点日前推 45 个自然日（常规场景一次请求即含前一根）。 */
const QUOTE_WINDOW_DAYS = 45;

function fetchQuoteBars(instrumentId: number, startDate: string, endDate: string): Promise<InstrumentChart> {
	return fetchInstrumentBars(String(instrumentId), {
		adjustment: "none",
		allowExperimental: false,
		endDate,
		period: "daily",
		startDate,
	});
}

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
export function WatchlistPage({ sourceJudgmentId = "" }: { readonly sourceJudgmentId?: string }) {
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
	// 最近完整交易日锚点只认 calendar 数据集最新一次成功摄取的交易日。
	// 没有成功锚点时保持未解析、不发行情请求：服务端对超出日历 authority
	// 的窗口逐自然日 fail-closed（422），用客户端"今天"猜锚点只会让每行
	// 永久「行情读取失败」且重试无效——锚点未落定在行级如实展示。
	const observationQuery = useCalendarStatus();
	const anchorDate =
		observationQuery.data?.latest_status === "success" && observationQuery.data.latest_date
			? observationQuery.data.latest_date
			: null;
	// 行情列复用既有日 K 合同，涨跌口径与锚定图表一致：最近一根对
	// 「观察日前一年窗口内」前一根收盘的变化。常规 45 天窄窗拿到前一根
	// 即止（一次请求）；复牌等长间隔场景窄窗只剩一根时，改用图表同一
	// 观察窗（观察日−1 年）补取，保证表图数字同源；停牌超过一年时
	// 两个窗口同样只有一根，表与图同为 —。
	const resolveQuote = async (instrumentId: number, anchor: string): Promise<MarketQuoteSnapshot | null> => {
		const narrow = await fetchQuoteBars(instrumentId, dateDaysBefore(anchor, QUOTE_WINDOW_DAYS), anchor);
		const lastNarrow = narrow.bars.at(-1);
		if (!lastNarrow) return null;
		let bars = narrow.bars;
		if (narrow.bars.length < 2) {
			const wide = await fetchQuoteBars(instrumentId, dateYearsBefore(lastNarrow.trade_date, 1), anchor);
			bars = wide.bars;
		}
		const latest = bars.at(-1);
		if (!latest) return null;
		const previous = bars.at(-2);
		const change = previous ? latest.close - previous.close : null;
		// 前收盘为 0 视为涨跌幅不可算（与图表 primaryAnswerFromBars 真值检查同口径）。
		const changePercent = change !== null && previous?.close ? (change / previous.close) * 100 : null;
		return { change, changePercent, close: latest.close, tradeDate: latest.trade_date };
	};
	return (
		<WatchlistView
			observationQuery={observationQuery}
			quote={{ anchorDate, anchorPending: observationQuery.isLoading, resolve: resolveQuote }}
			resolveEntry={resolveEntry}
			searchCatalog={searchCatalog}
			sourceJudgmentId={sourceJudgmentId}
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
