import type {
	DataProvider,
	Pipeline,
	PipelineRun,
	PlatformAlert,
	PlatformHealthResponse,
	ResourceUsage,
} from "@/types";

export const mockPlatformHealth: PlatformHealthResponse = {
	freshness: 98.5,
	completeness: 99.2,
	accuracy: 97.8,
	jobsStatus: {
		running: 3,
		queued: 1,
		failed: 0,
	},
};

export const mockProviders: readonly DataProvider[] = [
	{
		name: "tushare",
		status: "healthy",
		latency: 45,
		missingRate: 0.02,
		anomalyRate: 0.01,
		lastSync: "2026-04-08T09:30:00Z",
		endpoints: [
			{ name: "daily", url: "https://api.tushare.pro", latency: 42 },
			{ name: "realtime", url: "https://api.tushare.pro", latency: 67 },
		],
	},
	{
		name: "MiniQMT",
		status: "healthy",
		latency: 12,
		missingRate: 0,
		anomalyRate: 0,
		lastSync: "2026-04-08T09:30:05Z",
		endpoints: [
			{ name: "quotes", url: "localhost:8090", latency: 8 },
			{ name: "orders", url: "localhost:8090", latency: 15 },
		],
	},
	{
		name: "FRED",
		status: "degraded",
		latency: 230,
		missingRate: 0.05,
		anomalyRate: 0.03,
		lastSync: "2026-04-08T08:00:00Z",
		endpoints: [{ name: "macro", url: "https://api.stlouisfed.org", latency: 230 }],
	},
];

export const mockPipelines: readonly Pipeline[] = [
	{
		id: "pipe-001",
		name: "A股日线同步",
		status: "success",
		lastRun: "2026-04-08T09:00:00Z",
		nextRun: "2026-04-08T15:30:00Z",
		duration: 45,
		recordsProcessed: 5200,
		errorCount: 0,
	},
	{
		id: "pipe-002",
		name: "分钟线采集",
		status: "running",
		lastRun: "2026-04-08T09:30:00Z",
		duration: 120,
		recordsProcessed: 15000,
		errorCount: 2,
	},
	{
		id: "pipe-003",
		name: "财务数据更新",
		status: "warning",
		lastRun: "2026-04-07T20:00:00Z",
		nextRun: "2026-04-08T20:00:00Z",
		duration: 300,
		recordsProcessed: 8900,
		errorCount: 5,
	},
];

export const mockPipelineRuns: readonly PipelineRun[] = [
	{
		id: "run-001",
		pipelineId: "pipe-001",
		status: "success",
		startTime: "2026-04-08T09:00:00Z",
		endTime: "2026-04-08T09:00:45Z",
		duration: 45,
		recordsProcessed: 5200,
		errorCount: 0,
	},
	{
		id: "run-002",
		pipelineId: "pipe-002",
		status: "running",
		startTime: "2026-04-08T09:30:00Z",
		duration: 120,
		recordsProcessed: 15000,
		errorCount: 2,
		errorMessages: ["超时重试 2 次", "数据缺失补全"],
	},
];

export const mockPlatformAlerts: readonly PlatformAlert[] = [
	{
		id: "alert-001",
		severity: "critical",
		title: "FRED 数据源连接超时",
		description: "FRED API 响应时间超过 200ms 阈值",
		source: "fired",
		createdAt: "2026-04-08T08:15:00Z",
		status: "active",
	},
	{
		id: "alert-002",
		severity: "warning",
		title: "分钟线采集数据缺失",
		description: "3 只标的分钟线数据不完整",
		source: "data-quality",
		createdAt: "2026-04-08T09:10:00Z",
		status: "acknowledged",
	},
	{
		id: "alert-003",
		severity: "info",
		title: "财务数据定时更新完成",
		description: "8920 条记录已更新",
		source: "pipeline",
		createdAt: "2026-04-07T20:05:00Z",
		status: "resolved",
	},
];

export const mockPlatformResources: readonly ResourceUsage[] = [
	{ resource: "CPU", usage: 42, limit: 100, unit: "%", status: "healthy" },
	{ resource: "Memory", usage: 6.2, limit: 16, unit: "GB", status: "healthy" },
	{ resource: "Disk", usage: 128, limit: 500, unit: "GB", status: "healthy" },
	{
		resource: "API Quota (tushare)",
		usage: 4500,
		limit: 10000,
		unit: "req/day",
		status: "degraded",
	},
];
