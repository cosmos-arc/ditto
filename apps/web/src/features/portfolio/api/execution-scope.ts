import { DEFAULT_STRATEGY_ID } from "./query-keys";

export type TradingExecutionScope = {
	readonly strategyId: string;
	readonly accountId?: string;
	readonly tradeDate?: string;
};

function nonEmpty(value: string | null | undefined): string | undefined {
	const normalized = value?.trim();
	return normalized ? normalized : undefined;
}

/**
 * R1 execution scope is explicit and operator-controlled. URL parameters make
 * the selection linkable/auditable while still keeping the published ETF seed
 * as the first-run strategy default. No account is guessed.
 */
export function resolveTradingExecutionScope(overrides: Partial<TradingExecutionScope> = {}): TradingExecutionScope {
	const search = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
	return {
		strategyId: nonEmpty(overrides.strategyId) ?? nonEmpty(search.get("strategy_id")) ?? DEFAULT_STRATEGY_ID,
		accountId: nonEmpty(overrides.accountId) ?? nonEmpty(search.get("account_id")),
		tradeDate: nonEmpty(overrides.tradeDate) ?? nonEmpty(search.get("trade_date")),
	};
}
