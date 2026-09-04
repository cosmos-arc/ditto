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
	dailyDecisionV3: (strategyId = DEFAULT_STRATEGY_ID, tradeDate?: string, accountId?: string) =>
		[
			...tradingKeys.all,
			"daily-decision",
			"v3",
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
	portfolioComparison: (identity: {
		readonly strategy_id: string;
		readonly model_portfolio_id: string;
		readonly paper_account_id: string;
		readonly manual_account_id: string;
		readonly paper_session_id: string;
		readonly as_of: string;
		readonly knowledge_cutoff: string;
		readonly publication_cutoff: string;
		readonly source_snapshot_ids: readonly string[];
		readonly valuation_snapshot_id?: string | null;
	}) =>
		[
			...tradingKeys.all,
			"portfolio-comparison",
			identity.strategy_id,
			identity.model_portfolio_id,
			identity.paper_account_id,
			identity.manual_account_id,
			identity.paper_session_id,
			identity.as_of,
			identity.knowledge_cutoff,
			identity.publication_cutoff,
			[...identity.source_snapshot_ids].sort().join("|"),
			identity.valuation_snapshot_id ?? "valuation-unresolved",
		] as const,
	manualLedger: (accountId: string, asOf: string) => [...tradingKeys.all, "manual-account", accountId, asOf] as const,
	paperLedger: (accountId: string, asOf: string) => [...tradingKeys.all, "paper-account", accountId, asOf] as const,
	paperSession: (sessionId: string) => [...tradingKeys.all, "paper-session", sessionId] as const,
} as const;
