export const DEFAULT_STRATEGY_ID = "seed_etf_industry_rotation";

export const tradingKeys = {
	all: ["trading"] as const,
	dailyDecision: (strategyId = DEFAULT_STRATEGY_ID, tradeDate?: string, accountId?: string) =>
		[
			...tradingKeys.all,
			"daily-decision",
			strategyId,
			tradeDate ?? "latest",
			accountId ?? "account-unselected",
		] as const,
	signals: (strategyId = DEFAULT_STRATEGY_ID, signalDate?: string) =>
		[...tradingKeys.all, "signals", strategyId, signalDate ?? "latest"] as const,
	intents: (strategyId = DEFAULT_STRATEGY_ID, status?: string) =>
		[...tradingKeys.all, "intents", strategyId, status ?? "all"] as const,
	fills: (strategyId = DEFAULT_STRATEGY_ID, startDate?: string, endDate?: string) =>
		[...tradingKeys.all, "fills", strategyId, startDate ?? "start", endDate ?? "end"] as const,
	positions: (strategyId = DEFAULT_STRATEGY_ID, snapshotDate?: string) =>
		[...tradingKeys.all, "positions", strategyId, snapshotDate ?? "latest"] as const,
	pnl: (strategyId = DEFAULT_STRATEGY_ID, snapshotDate?: string) =>
		[...tradingKeys.all, "pnl", strategyId, snapshotDate ?? "latest"] as const,
	deviation: (strategyId = DEFAULT_STRATEGY_ID, signalDate?: string) =>
		[...tradingKeys.all, "deviation", strategyId, signalDate ?? "latest"] as const,
	comparison: (strategyId = DEFAULT_STRATEGY_ID) => [...tradingKeys.all, "comparison", strategyId] as const,
} as const;
