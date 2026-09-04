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

/** 实验列表项（R3 live-shape，基于 `ExperimentSummaryResponse`）。完整工作台属 T19。 */
export type ExperimentListItem = {
	readonly experimentId: string;
	readonly status: string;
	readonly desiredState: string;
	readonly stage: string;
	readonly failureCode: string | null;
	readonly queueOrdinal: number | null;
	readonly revision: number;
	readonly createdAt: string;
	readonly updatedAt: string;
};

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
