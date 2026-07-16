import type { ApprovalStatus, PaginatedRequest, PaginatedResponse, RunStatus } from "./common";

// === Request Types ===

export type GetResearchPulseRequest = undefined;

export type GetFactorsRequest = PaginatedRequest;

export type GetResearchRunsRequest = PaginatedRequest;

export type GetExperimentsRequest = PaginatedRequest;

export type GetReviewQueueRequest = PaginatedRequest;

export type PostBacktestRequest = {
	readonly strategyId: string;
	readonly universe: string;
	readonly startDate: string;
	readonly endDate: string;
	readonly benchmark: string;
	readonly initialCapital: number;
	readonly costModel: {
		readonly commissionRate: number;
		readonly stampDuty: number;
		readonly slippage: number;
	};
};

export type GetBacktestResultRequest = {
	readonly jobId: string;
};

export type GetStrategyRequest = {
	readonly id: string;
};

export type PutStrategyRequest = {
	readonly id: string;
	readonly name?: string;
	readonly factors?: readonly string[];
	readonly pipeline?: StrategyPipeline;
	readonly universe?: string;
	readonly weightConfig?: Readonly<Record<string, number>>;
	readonly riskRules?: readonly RiskRule[];
	readonly code?: string;
};

export type ValidateStrategyRequest = {
	readonly code?: string;
	readonly pipeline?: StrategyPipeline;
};

export type DryRunStrategyRequest = {
	readonly strategy: StrategySnapshot;
	readonly universe: string;
	readonly period: string;
};

export type GetStrategyVersionsRequest = {
	readonly id: string;
};

export type GetFactorLibraryRequest = PaginatedRequest;

export type GetRegimeCurrentRequest = undefined;

export type GetRegimeDriversRequest = undefined;

export type GetRegimeHistoryRequest = PaginatedRequest;

export type GetRegimeStrategyImpactRequest = undefined;

// === Response Types ===

/** 研究脉动 */
export type ResearchPulseResponse = {
	readonly activeFactors: number;
	readonly degradingFactors: number;
	readonly failedFactors: number;
	readonly reviewQueueLength: number;
};

export type GetResearchPulseResponse = ResearchPulseResponse;

/** 因子列表 */
export type Factor = {
	readonly id: string;
	readonly name: string;
	readonly family: string;
	readonly ic: number;
	readonly ir: number;
	readonly decay: number;
	readonly turnover: number;
	readonly coverage: number;
	readonly healthStatus: RunStatus;
	readonly lastUpdated: string;
	readonly sharpe?: number;
	readonly universe?: string;
};

export type GetFactorsResponse = PaginatedResponse<Factor>;

/** 因子 IC 时序数据点 */
export type FactorICPoint = {
	readonly date: string;
	readonly ic: number;
	readonly ir: number;
};

/** 因子诊断项 */
export type FactorDiagnostic = {
	readonly name: string;
	readonly result: "pass" | "warning" | "fail";
	readonly value: number;
	readonly threshold: number;
};

/** 因子详情 */
export type FactorDetailResponse = {
	readonly factor: Factor;
	readonly history: readonly FactorICPoint[];
	readonly diagnostics: readonly FactorDiagnostic[];
};

/** 因子衰减分析数据点 */
export type FactorDecayPoint = {
	readonly lag: number;
	readonly ic: number;
};

/** 因子 IR 分布数据点 */
export type FactorIRDistributionPoint = {
	readonly range: string;
	readonly count: number;
};

/** 因子分析 */
export type FactorAnalysisResponse = {
	readonly icTimeSeries: readonly FactorICPoint[];
	readonly irDistribution: readonly FactorIRDistributionPoint[];
	readonly decayAnalysis: readonly FactorDecayPoint[];
	readonly sectorExposure: readonly {
		readonly sector: string;
		readonly exposure: number;
	}[];
};

/** 研究运行 */
export type ResearchRun = {
	readonly id: string;
	readonly name: string;
	readonly type: "backtest" | "factor_analysis" | "experiment";
	readonly status: RunStatus;
	readonly startTime: string;
	readonly endTime?: string;
	readonly keyMetric?: string;
};

export type GetResearchRunsResponse = PaginatedResponse<ResearchRun>;

/** 实验 */
export type Experiment = {
	readonly id: string;
	readonly name: string;
	readonly status: RunStatus;
	readonly factors: readonly string[];
	readonly createdAt: string;
};

export type GetExperimentsResponse = PaginatedResponse<Experiment>;

/** 审核队列项 */
export type ReviewQueueItem = {
	readonly id: string;
	readonly type: "factor" | "strategy" | "experiment";
	readonly name: string;
	readonly status: ApprovalStatus;
	readonly submittedAt: string;
};

export type GetReviewQueueResponse = PaginatedResponse<ReviewQueueItem>;

/** 回测提交响应 */
export type PostBacktestResponse = {
	readonly jobId: string;
};

/** 回测结果 */
export type BacktestStatistics = {
	readonly sharpe: number;
	readonly mdd: number;
	readonly sortino: number;
	readonly calmar: number;
	readonly winRate: number;
	readonly plRatio: number;
	readonly turnover: number;
	readonly annualizedReturn: number;
};

export type NavPoint = {
	readonly date: string;
	readonly nav: number;
	readonly drawdown: number;
	readonly benchmark?: number;
};

export type Holding = {
	readonly date: string;
	readonly code: string;
	readonly name: string;
	readonly weight: number;
	readonly shares: number;
};

export type BacktestTrade = {
	readonly id: string;
	readonly date: string;
	readonly code: string;
	readonly name: string;
	readonly side: "BUY" | "SELL";
	readonly price: number;
	readonly shares: number;
	readonly commission: number;
	readonly pnl: number;
};

export type MonthlyReturn = {
	readonly month: string;
	readonly return: number;
	readonly benchmarkReturn: number;
};

export type GetBacktestResultResponse = {
	readonly status: RunStatus;
	readonly progress: number;
	readonly navSeries: readonly NavPoint[];
	readonly holdings: readonly Holding[];
	readonly trades: readonly BacktestTrade[];
	readonly monthlyReturns: readonly MonthlyReturn[];
	readonly statistics: BacktestStatistics;
};

/** 策略管道节点 */
export type StrategyPipelineNode = {
	readonly id: string;
	readonly name: string;
	readonly type: string;
	readonly config: Readonly<Record<string, unknown>>;
};

/** 策略管道 */
export type StrategyPipeline = {
	readonly nodes: readonly StrategyPipelineNode[];
	readonly edges: readonly {
		readonly from: string;
		readonly to: string;
	}[];
};

/** 风控规则 */
export type RiskRule = {
	readonly name: string;
	readonly type: string;
	readonly params: Readonly<Record<string, number>>;
	readonly enabled: boolean;
};

/** 策略快照（用于 dry-run） */
export type StrategySnapshot = {
	readonly factors: readonly string[];
	readonly pipeline: StrategyPipeline;
	readonly weightConfig: Readonly<Record<string, number>>;
	readonly riskRules: readonly RiskRule[];
	readonly code?: string;
};

/** 策略详情 */
export type StrategyDetail = {
	readonly id: string;
	readonly name: string;
	readonly version: number;
	readonly mode: "form" | "code";
	readonly status: RunStatus;
	readonly factors: readonly string[];
	readonly pipeline: StrategyPipeline;
	readonly universe: string;
	readonly weightConfig: Readonly<Record<string, number>>;
	readonly riskRules: readonly RiskRule[];
	readonly code?: string;
	readonly savedAt: string;
};

export type GetStrategyResponse = StrategyDetail;
export type PutStrategyResponse = StrategyDetail;

/** 策略校验结果 */
export type ValidateStrategyResponse = {
	readonly valid: boolean;
	readonly errors: readonly string[];
	readonly warnings: readonly string[];
};

/** 策略 dry-run 结果 */
export type DryRunResult = {
	readonly previewResults: {
		readonly navSeries: readonly NavPoint[];
		readonly statistics: Partial<BacktestStatistics>;
	};
	readonly warnings: readonly string[];
};

export type DryRunStrategyResponse = DryRunResult;

/** 策略版本 */
export type StrategyVersion = {
	readonly version: number;
	readonly code: string;
	readonly savedAt: string;
	readonly changeNote?: string;
};

export type GetStrategyVersionsResponse = {
	readonly versions: readonly StrategyVersion[];
};

/** 因子库 */
export type FactorLibraryItem = {
	readonly id: string;
	readonly name: string;
	readonly family: string;
	readonly description: string;
	readonly source: string;
	readonly preprocessorOptions: readonly {
		readonly name: string;
		readonly params: Readonly<Record<string, unknown>>;
	}[];
};

export type GetFactorLibraryResponse = PaginatedResponse<FactorLibraryItem>;

/** Regime 状态 */
export type RegimeState = "risk_on" | "risk_off" | "transition" | "volatile";

export type RegimeIndicator = {
	readonly name: string;
	readonly value: number;
	readonly normal: boolean;
	readonly description: string;
};

export type GetRegimeCurrentResponse = {
	readonly state: RegimeState;
	readonly confidence: number;
	readonly duration: number;
	readonly keyIndicators: readonly RegimeIndicator[];
};

/** Regime 驱动因子 */
export type RegimeDriver = {
	readonly name: string;
	readonly value: number;
	readonly trend: "up" | "down" | "flat";
	readonly impact: "positive" | "negative" | "neutral";
};

export type GetRegimeDriversResponse = {
	readonly drivers: readonly RegimeDriver[];
};

/** Regime 历史切换 */
export type RegimeSwitch = {
	readonly date: string;
	readonly fromState: RegimeState;
	readonly toState: RegimeState;
	readonly trigger: string;
	readonly confidence: number;
};

export type GetRegimeHistoryResponse = PaginatedResponse<RegimeSwitch>;

/** Regime 对策略的影响 */
export type RegimeStrategyImpact = {
	readonly id: string;
	readonly name: string;
	readonly performance: number;
	readonly adjustmentSuggestion: string;
};

export type GetRegimeStrategyImpactResponse = {
	readonly strategies: readonly RegimeStrategyImpact[];
};
