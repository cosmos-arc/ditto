import type {
	ResearchPulseResponse,
	GetFactorsResponse,
	GetResearchRunsResponse,
	GetExperimentsResponse,
	GetReviewQueueResponse,
	FactorDetailResponse,
	FactorAnalysisResponse,
} from "@/types";

export const mockResearchPulse: ResearchPulseResponse = {
	activeFactors: 42,
	degradingFactors: 3,
	failedFactors: 1,
	reviewQueueLength: 5,
};

export const mockFactors: GetFactorsResponse = {
	items: [
		{ id: "f-001", name: "动量因子", family: "技术面", ic: 0.052, ir: 0.85, decay: 5, turnover: 0.32, coverage: 0.92, healthStatus: "completed", lastUpdated: "2026-04-08T09:00:00Z" },
		{ id: "f-002", name: "价值因子", family: "基本面", ic: 0.041, ir: 0.72, decay: 10, turnover: 0.18, coverage: 0.88, healthStatus: "completed", lastUpdated: "2026-04-08T09:00:00Z" },
		{ id: "f-003", name: "波动率因子", family: "风险面", ic: 0.038, ir: 0.65, decay: 3, turnover: 0.45, coverage: 0.95, healthStatus: "running", lastUpdated: "2026-04-08T08:30:00Z" },
		{ id: "f-004", name: "情绪因子", family: "另类", ic: 0.025, ir: 0.42, decay: 7, turnover: 0.55, coverage: 0.78, healthStatus: "warning", lastUpdated: "2026-04-07T20:00:00Z" },
		{ id: "f-005", name: "北向资金因子", family: "资金流", ic: 0.015, ir: 0.30, decay: 2, turnover: 0.60, coverage: 0.70, healthStatus: "failed", lastUpdated: "2026-04-07T18:00:00Z" },
	],
	total: 42,
	page: 1,
	pageSize: 20,
};

export const mockResearchRuns: GetResearchRunsResponse = {
	items: [
		{ id: "run-001", name: "动量策略 v3 回测", type: "backtest", status: "completed", startTime: "2026-04-08T01:00:00Z", endTime: "2026-04-08T02:30:00Z", keyMetric: "Sharpe 1.82" },
		{ id: "run-002", name: "因子 IC 日报", type: "factor_analysis", status: "completed", startTime: "2026-04-08T09:00:00Z", endTime: "2026-04-08T09:15:00Z", keyMetric: "42 因子" },
		{ id: "run-003", name: "多因子组合实验", type: "experiment", status: "running", startTime: "2026-04-08T09:30:00Z" },
	],
	total: 15,
	page: 1,
	pageSize: 20,
};

export const mockExperiments: GetExperimentsResponse = {
	items: [
		{ id: "exp-001", name: "AI 选股 vs 传统多因子", status: "completed", factors: ["动量因子", "情绪因子", "北向资金因子"], createdAt: "2026-04-07T14:00:00Z" },
		{ id: "exp-002", name: "行业轮动策略 A/B 测试", status: "running", factors: ["行业动量", "资金流"], createdAt: "2026-04-08T10:00:00Z" },
	],
	total: 8,
	page: 1,
	pageSize: 20,
};

export const mockReviewQueue: GetReviewQueueResponse = {
	items: [
		{ id: "rev-001", type: "factor", name: "情绪因子 v2", status: "pending", submittedAt: "2026-04-08T08:00:00Z" },
		{ id: "rev-002", type: "strategy", name: "动量突破 v4", status: "pending", submittedAt: "2026-04-08T07:30:00Z" },
		{ id: "rev-003", type: "experiment", name: "Q2 因子权重优化", status: "approved", submittedAt: "2026-04-07T16:00:00Z" },
	],
	total: 5,
	page: 1,
	pageSize: 20,
} as const;

// === 因子详情 Mock Data ===

export const mockFactorDetail: FactorDetailResponse = {
	factor: {
		id: "f-001",
		name: "动量因子",
		family: "技术面",
		ic: 0.052,
		ir: 0.85,
		decay: 5,
		turnover: 0.32,
		coverage: 0.92,
		healthStatus: "completed",
		lastUpdated: "2026-04-08T09:00:00Z",
	},
	history: [
		{ date: "2026-04-08", ic: 0.058, ir: 0.92 },
		{ date: "2026-04-07", ic: 0.045, ir: 0.78 },
		{ date: "2026-04-04", ic: 0.062, ir: 0.95 },
		{ date: "2026-04-03", ic: 0.038, ir: 0.68 },
		{ date: "2026-04-02", ic: 0.051, ir: 0.82 },
		{ date: "2026-04-01", ic: 0.042, ir: 0.75 },
		{ date: "2026-03-31", ic: 0.055, ir: 0.88 },
		{ date: "2026-03-28", ic: 0.048, ir: 0.80 },
		{ date: "2026-03-27", ic: 0.060, ir: 0.90 },
		{ date: "2026-03-26", ic: 0.035, ir: 0.62 },
	] as const,
	diagnostics: [
		{ name: "衰减测试", result: "pass", value: 0.038, threshold: 0.020 },
		{ name: "换手率测试", result: "pass", value: 0.32, threshold: 0.50 },
		{ name: "覆盖率测试", result: "pass", value: 0.92, threshold: 0.80 },
		{ name: "多头收益测试", result: "pass", value: 0.015, threshold: 0.008 },
		{ name: "空头收益测试", result: "warning", value: -0.003, threshold: -0.005 },
	] as const,
} as const;

// === 因子分析 Mock Data ===

export const mockFactorAnalysis: FactorAnalysisResponse = {
	icTimeSeries: [
		{ date: "2026-04-08", ic: 0.058, ir: 0.92 },
		{ date: "2026-04-07", ic: 0.045, ir: 0.78 },
		{ date: "2026-04-04", ic: 0.062, ir: 0.95 },
		{ date: "2026-04-03", ic: 0.038, ir: 0.68 },
		{ date: "2026-04-02", ic: 0.051, ir: 0.82 },
		{ date: "2026-04-01", ic: 0.042, ir: 0.75 },
		{ date: "2026-03-31", ic: 0.055, ir: 0.88 },
		{ date: "2026-03-28", ic: 0.048, ir: 0.80 },
		{ date: "2026-03-27", ic: 0.060, ir: 0.90 },
		{ date: "2026-03-26", ic: 0.035, ir: 0.62 },
		{ date: "2026-03-25", ic: 0.050, ir: 0.85 },
		{ date: "2026-03-24", ic: 0.043, ir: 0.72 },
	] as const,
	irDistribution: [
		{ range: "< 0", count: 5 },
		{ range: "0 ~ 0.3", count: 12 },
		{ range: "0.3 ~ 0.5", count: 28 },
		{ range: "0.5 ~ 0.7", count: 35 },
		{ range: "0.7 ~ 1.0", count: 18 },
		{ range: "> 1.0", count: 2 },
	] as const,
	decayAnalysis: [
		{ lag: 0, ic: 0.052 },
		{ lag: 1, ic: 0.048 },
		{ lag: 2, ic: 0.042 },
		{ lag: 3, ic: 0.035 },
		{ lag: 5, ic: 0.022 },
		{ lag: 7, ic: 0.015 },
		{ lag: 10, ic: 0.008 },
		{ lag: 15, ic: 0.002 },
		{ lag: 20, ic: -0.003 },
	] as const,
	sectorExposure: [
		{ sector: "科技", exposure: 0.35 },
		{ sector: "新能源", exposure: 0.28 },
		{ sector: "消费", exposure: 0.18 },
		{ sector: "医药", exposure: 0.12 },
		{ sector: "金融", exposure: -0.05 },
		{ sector: "地产", exposure: -0.08 },
		{ sector: "周期", exposure: 0.15 },
		{ sector: "制造", exposure: 0.22 },
	] as const,
} as const;
