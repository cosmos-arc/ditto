import type { MarketCalendarStatus, MarketContext } from "../api/market-evidence";

/** Query state supplied by an app workflow to a Markets-owned view. */
export interface MarketQueryResult<T> {
	readonly data: T | undefined;
	readonly isError: boolean;
	readonly isLoading: boolean;
	readonly refetch: () => unknown;
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

export type MarketCatalogQuery = MarketQueryResult<MarketCatalog>;
export type MarketCalendarStatusQuery = MarketQueryResult<MarketCalendarStatus>;
export type MarketContextQuery = MarketQueryResult<MarketContext>;
