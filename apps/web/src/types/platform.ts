import type {
	HealthStatus,
	PaginatedResponse,
	Priority,
	Severity,
} from "./common";

// === Request Types ===

export type GetPlatformHealthRequest = undefined;

export type GetProvidersRequest = undefined;

export type GetPipelinesRequest = PaginatedRequest;

export type GetPipelineRunsRequest = {
	readonly pipelineId: string;
} & PaginatedRequest;

export type GetPlatformAlertsRequest = PaginatedRequest;

export type GetPlatformResourcesRequest = undefined;

export type HandleAlertRequest = {
	readonly action: "acknowledge" | "resolve" | "escalate";
	readonly note?: string;
};

export type RerunPipelineRequest = {
	readonly reason?: string;
};

// === Response Types ===

/** Platform 健康概览 */
export type PlatformHealthResponse = {
	readonly freshness: number;
	readonly completeness: number;
	readonly accuracy: number;
	readonly jobsStatus: {
		readonly running: number;
		readonly queued: number;
		readonly failed: number;
	};
};

/** 数据提供者端点 */
export type ProviderEndpoint = {
	readonly name: string;
	readonly url: string;
	readonly latency: number;
};

/** 数据提供者 */
export type DataProvider = {
	readonly name: string;
	readonly status: HealthStatus;
	readonly latency: number;
	readonly missingRate: number;
	readonly anomalyRate: number;
	readonly lastSync: string;
	readonly endpoints: readonly ProviderEndpoint[];
};

export type GetProvidersResponse = {
	readonly providers: readonly DataProvider[];
};

/** 管道状态 */
export type PipelineStatus =
	| "idle"
	| "running"
	| "success"
	| "failed"
	| "warning";

/** 数据管道 */
export type Pipeline = {
	readonly id: string;
	readonly name: string;
	readonly status: PipelineStatus;
	readonly lastRun: string;
	readonly nextRun?: string;
	readonly duration: number;
	readonly recordsProcessed: number;
	readonly errorCount: number;
};

export type GetPipelinesResponse = PaginatedResponse<Pipeline>;

/** 管道运行记录 */
export type PipelineRun = {
	readonly id: string;
	readonly pipelineId: string;
	readonly status: PipelineStatus;
	readonly startTime: string;
	readonly endTime?: string;
	readonly duration: number;
	readonly recordsProcessed: number;
	readonly errorCount: number;
	readonly errorMessages?: readonly string[];
};

export type GetPipelineRunsResponse = PaginatedResponse<PipelineRun>;

/** 平台告警 */
export type PlatformAlert = {
	readonly id: string;
	readonly severity: Severity;
	readonly title: string;
	readonly description: string;
	readonly source: string;
	readonly createdAt: string;
	readonly status: "active" | "acknowledged" | "resolved";
};

export type GetPlatformAlertsResponse = PaginatedResponse<PlatformAlert>;

/** 资源使用情况 */
export type ResourceUsage = {
	readonly resource: string;
	readonly usage: number;
	readonly limit: number;
	readonly unit: string;
	readonly status: HealthStatus;
};

export type GetPlatformResourcesResponse = {
	readonly resources: readonly ResourceUsage[];
};
