import type { MarketCalendarStatus, MarketContext } from "../api/market-evidence";

/** Query state supplied by an app workflow to a Markets-owned view. */
export interface MarketQueryResult<T> {
	readonly data: T | undefined;
	readonly isError: boolean;
	readonly isLoading: boolean;
	readonly refetch: () => unknown;
}

/**
 * 最近完整交易日的展示标签：calendar 数据集最新一次成功摄取的交易日；
 * 失败/缺失按真实结果降级（未解析/最新摄取失败/未报告），不伪装完整。
 * A 股周末从不交易：latest_date 落在周末时明确标注「非交易日」，
 * 不把周末日期直接称作最近完整交易日。
 */
export function observationAnchorLabel(
	status: MarketCalendarStatus | undefined,
	isError: boolean,
	isLoading: boolean,
): string {
	if (isLoading) return "解析中";
	if (isError || !status) return "未解析";
	if (status.latest_status === "success" && status.latest_date) {
		const weekday = new Date(`${status.latest_date}T00:00:00Z`).getUTCDay();
		return weekday === 0 || weekday === 6 ? `${status.latest_date}（非交易日）` : status.latest_date;
	}
	if (status.latest_status === "failed") return `最新摄取失败（${status.latest_date ?? "无日期"}）`;
	return "未报告";
}

/** Minimal instrument projection rendered by Markets pages. */
export interface MarketCatalogInstrument {
	readonly asset_class: string;
	readonly exchange: string;
	readonly instrument_id: number;
	readonly is_active: boolean;
	readonly name: string;
	readonly ticker: string;
}

export interface MarketCatalog {
	readonly items: readonly MarketCatalogInstrument[];
	readonly total: number;
}

/** Calendar dataset ingestion status projection rendered by the calendar page. */
export type { MarketCalendarStatus } from "../api/market-evidence";

/**
 * 最新可见行情快照（最近一根日 K 收盘与对前一根的涨跌），由 workflow 从
 * 既有行情合同装配；markets 能力只渲染，不重算金融口径。
 */
export interface MarketQuoteSnapshot {
	readonly change: number | null;
	readonly changePercent: number | null;
	readonly close: number;
	readonly tradeDate: string;
}

/** 自选行情解析由 workflow 注入（markets 能力不依赖 instruments 能力）。 */
export type WatchlistQuoteFn = (instrumentId: number, anchorDate: string) => Promise<MarketQuoteSnapshot | null>;

export type MarketCatalogQuery = MarketQueryResult<MarketCatalog>;
export type MarketCalendarStatusQuery = MarketQueryResult<MarketCalendarStatus>;
export type MarketContextQuery = MarketQueryResult<MarketContext>;
