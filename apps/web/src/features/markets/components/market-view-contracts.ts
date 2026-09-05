import type { MarketContext } from "../api/market-evidence";

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

/** Minimal Data Product coverage projection rendered by the calendar page. */
export interface MarketCalendarCoverage {
	readonly actual_partitions: number;
	readonly certified_from: string | null;
	readonly complete_from: string | null;
	readonly expected_partitions: number;
	readonly raw_from: string | null;
	readonly unapproved_gaps: readonly string[];
}

export type MarketCatalogQuery = MarketQueryResult<MarketCatalog>;
export type MarketCalendarCoverageQuery = MarketQueryResult<MarketCalendarCoverage>;
export type MarketContextQuery = MarketQueryResult<MarketContext>;
