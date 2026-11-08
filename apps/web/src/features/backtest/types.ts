export interface BacktestRun {
	readonly runId: string;
	readonly strategyId: string;
	readonly strategyVersion: string;
	readonly mode: string;
	readonly status: string;
	readonly startedAt: string;
	readonly completedAt: string;
	readonly errorMessage: string;
	readonly parentRunId: string;
	readonly benchmarkReturn: number | null;
	readonly progressPct: number;
	readonly currentStep: string;
	readonly completedDays: number;
	readonly totalDays: number;
}

export interface BacktestAlphaStats {
	readonly annualizedReturn: number;
	readonly annualizedVolatility: number;
	readonly sharpeRatio: number;
	readonly sortinoRatio: number;
	readonly maxDrawdown: number;
	readonly maxDrawdownDurationDays: number;
	readonly calmarRatio: number;
	readonly informationRatio: number | null;
	readonly trackingError: number | null;
	readonly beta: number | null;
	readonly alphaAnnualized: number | null;
	readonly totalTurnover: number;
	readonly avgTurnoverPerRebalance: number;
	readonly totalFees: number;
	readonly netReturnAfterCost: number;
	readonly costDrag: number;
}

export interface BacktestTradeStats {
	readonly totalTrades: number;
	readonly longTrades: number;
	readonly shortTrades: number;
	readonly winTrades: number;
	readonly lossTrades: number;
	/** Percentage points, matching the engine: 58.33 means 58.33%. */
	readonly winRate: number;
	readonly profitFactor: number;
	readonly avgWin: number;
	readonly avgLoss: number;
	readonly avgWinLossRatio: number;
	readonly maxConsecutiveWins: number;
	readonly maxConsecutiveLosses: number;
	readonly avgHoldingDays: number;
	readonly medianHoldingDays: number;
	readonly bestTrade: number;
	readonly worstTrade: number;
	readonly avgTradeReturnPct: number;
}

export interface BacktestReport {
	readonly runId: string;
	readonly periodStart: string;
	readonly periodEnd: string;
	readonly initialCash: number;
	readonly finalNav: number;
	readonly rebalanceFreq: string;
	readonly alphaStats: BacktestAlphaStats | null;
	readonly tradeStats: BacktestTradeStats | null;
	readonly usageContext: BacktestUsageContext;
	readonly strategyPromotion: Readonly<Record<string, unknown>> | null;
	readonly pitPolicy: Readonly<Record<string, unknown>> | null;
}

export interface BacktestUsageContext {
	readonly intendedUse: string;
	readonly historicalAvailability: string;
	readonly samplePool: string;
	readonly inputInstrumentIds: readonly number[];
	readonly limitations: readonly string[];
}

export const legacyBacktestUsage: BacktestUsageContext = {
	intendedUse: "unclassified",
	historicalAvailability: "not_certified",
	samplePool: "unknown",
	inputInstrumentIds: [],
	limitations: [
		"旧报告未记录用途与样本池资格；严格历史可得性未认证。",
		"完成状态与 PIT fail_closed 策略均不构成来源认证；结果不自动授予策略晋级、信号启用或 Paper 授权。",
	],
};

export interface BacktestNavPoint {
	readonly tradeDate: string;
	readonly nav: number;
}

export interface BacktestBenchmark {
	readonly runId: string;
	readonly dates: readonly string[];
	readonly navs: readonly number[];
	readonly benchmarkReturn: number | null;
}

export interface BacktestTradeRecord {
	readonly tradeDate: string;
	readonly instrumentId: number;
	readonly direction: string;
	readonly entryDate: string;
	readonly exitDate: string;
	readonly entryPrice: number;
	readonly exitPrice: number;
	readonly quantity: number;
	readonly pnl: number;
}

export interface BacktestAuditRecord {
	readonly id: number;
	readonly runId: string;
	readonly tradeDate: string;
	readonly recordType: string;
	readonly instrumentId: number | null;
	readonly payload: Readonly<Record<string, unknown>>;
	readonly createdAt: string;
}
