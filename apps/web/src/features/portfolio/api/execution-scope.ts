import { DEFAULT_STRATEGY_ID } from "./query-keys";

export type TradingExecutionScope = {
	readonly strategyId: string;
	readonly accountId: string | undefined;
	readonly tradeDate: string | undefined;
};

type TradingExecutionScopeOverrides = {
	readonly strategyId?: string | undefined;
	readonly accountId?: string | undefined;
	readonly tradeDate?: string | undefined;
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
export function resolveTradingExecutionScope(overrides: TradingExecutionScopeOverrides = {}): TradingExecutionScope {
	const search = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
	return {
		strategyId: nonEmpty(overrides.strategyId) ?? nonEmpty(search.get("strategy_id")) ?? DEFAULT_STRATEGY_ID,
		accountId: nonEmpty(overrides.accountId) ?? nonEmpty(search.get("account_id")),
		tradeDate: nonEmpty(overrides.tradeDate) ?? nonEmpty(search.get("trade_date")),
	};
}
