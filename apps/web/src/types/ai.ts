import type {
	ApprovalStatus,
	PaginatedRequest,
	PaginatedResponse,
	RunStatus,
} from "./common";

// === Request Types ===

export type GetAiPulseRequest = undefined;

export type GetAgentQuickViewRequest = undefined;

export type GetCopilotQuickViewRequest = undefined;

export type PostCopilotChatRequest = {
	readonly sessionId?: string;
	readonly mode: "general" | "research" | "trading" | "coding";
	readonly message: string;
	readonly context?: readonly string[];
};

export type GetCopilotSessionsRequest = undefined;

export type PostCopilotSessionRequest = {
	readonly title?: string;
	readonly mode: "general" | "research" | "trading" | "coding";
};

export type GetCopilotSessionDetailRequest = {
	readonly id: string;
};

export type PostCopilotNoteRequest = {
	readonly sessionId: string;
	readonly content: string;
};

export type PostCopilotSendToWorkspaceRequest = {
	readonly sessionId: string;
	readonly messages: readonly string[];
	readonly target: "strategy" | "factor" | "backtest";
};

export type PostFactorDiscoveryRequest = {
	readonly description: string;
};

export type GetAgentPlansRequest = PaginatedRequest;

export type PostAgentPlanRequest = {
	readonly name: string;
	readonly objective: string;
	readonly scope: readonly string[];
	readonly constraints?: readonly string[];
};

export type GetAgentPlanDetailRequest = {
	readonly id: string;
};

export type GetAgentRunsRequest = PaginatedRequest;

export type PostAgentRunRerunRequest = {
	readonly id: string;
};

export type GetAgentFindingsRequest = PaginatedRequest;

export type PostAgentFindingApproveRequest = undefined;

export type PostAgentFindingRejectRequest = {
	readonly reason?: string;
};

export type GetAgentFindingTraceRequest = {
	readonly id: string;
};

// === Response Types ===

/** AI 脉动 */
export type AiPulseResponse = {
	readonly runningPlans: number;
	readonly pendingApprovals: number;
	readonly activeCopilotSessions: number;
};

/** Agent 快览 */
export type AgentPlanQuickView = {
	readonly id: string;
	readonly name: string;
	readonly status: string;
	readonly progress: number;
};

export type AgentFindingQuickView = {
	readonly id: string;
	readonly text: string;
	readonly confidence: number;
	readonly createdAt: string;
};

export type AgentCompletedQuickView = {
	readonly id: string;
	readonly name: string;
	readonly completedAt: string;
	readonly resultSummary: string;
};

export type GetAgentQuickViewResponse = {
	readonly plans: readonly AgentPlanQuickView[];
	readonly recentFindings: readonly AgentFindingQuickView[];
	readonly recentCompleted: readonly AgentCompletedQuickView[];
};

/** Copilot 快览 */
export type CopilotSessionQuickView = {
	readonly id: string;
	readonly title: string;
	readonly mode: string;
	readonly updatedAt: string;
	readonly messageCount: number;
};

export type CopilotOutputQuickView = {
	readonly id: string;
	readonly sessionId: string;
	readonly type: string;
	readonly summary: string;
	readonly createdAt: string;
};

export type CopilotNoteQuickView = {
	readonly id: string;
	readonly title: string;
	readonly content: string;
	readonly createdAt: string;
};

export type GetCopilotQuickViewResponse = {
	readonly sessions: readonly CopilotSessionQuickView[];
	readonly recentOutputs: readonly CopilotOutputQuickView[];
	readonly savedNotes: readonly CopilotNoteQuickView[];
};

/** Copilot SSE 响应 */
export type CopilotChatDelta = {
	readonly delta: string;
	readonly structuredOutput?: unknown;
};

/** Copilot 会话 */
export type CopilotMessage = {
	readonly id: string;
	readonly role: "user" | "assistant" | "system";
	readonly content: string;
	readonly structuredOutput?: unknown;
	readonly createdAt: string;
};

export type CopilotSession = {
	readonly id: string;
	readonly title: string;
	readonly mode: "general" | "research" | "trading" | "coding";
	readonly messages: readonly CopilotMessage[];
	readonly createdAt: string;
	readonly updatedAt: string;
};

export type GetCopilotSessionsResponse = {
	readonly sessions: readonly CopilotSession[];
};

export type PostCopilotSessionResponse = CopilotSession;
export type GetCopilotSessionDetailResponse = CopilotSession;

/** Copilot 笔记 */
export type PostCopilotNoteResponse = {
	readonly id: string;
	readonly sessionId: string;
	readonly content: string;
	readonly createdAt: string;
};

/** 发送到工作区 */
export type PostCopilotSendToWorkspaceResponse = {
	readonly success: boolean;
	readonly targetId?: string;
	readonly targetType?: string;
};

/** 因子发现 */
export type FactorHypothesis = {
	readonly name: string;
	readonly logic: string;
	readonly dataSource: string;
	readonly validationMethod: string;
};

export type PostFactorDiscoveryResponse = {
	readonly hypothesis: FactorHypothesis;
};

/** Agent 计划 */
export type AgentPlan = {
	readonly id: string;
	readonly name: string;
	readonly objective: string;
	readonly scope: readonly string[];
	readonly constraints: readonly string[];
	readonly status: RunStatus;
	readonly createdAt: string;
	readonly updatedAt: string;
};

export type GetAgentPlansResponse = PaginatedResponse<AgentPlan>;
export type PostAgentPlanResponse = AgentPlan;
export type GetAgentPlanDetailResponse = AgentPlan;

/** Agent 运行 */
export type AgentRun = {
	readonly id: string;
	readonly planId: string;
	readonly planName: string;
	readonly status: RunStatus;
	readonly stage: string;
	readonly progress: number;
	readonly startTime: string;
	readonly endTime?: string;
	readonly findingsCount: number;
};

export type GetAgentRunsResponse = PaginatedResponse<AgentRun>;
export type PostAgentRunRerunResponse = AgentRun;

/** Agent 发现 */
export type AgentFinding = {
	readonly id: string;
	readonly runId: string;
	readonly text: string;
	readonly confidence: number;
	readonly evidence: readonly string[];
	readonly impact: string;
	readonly status: ApprovalStatus;
	readonly createdAt: string;
};

export type GetAgentFindingsResponse = PaginatedResponse<AgentFinding>;

/** Agent 发现审批响应 */
export type PostAgentFindingApproveResponse = {
	readonly findingId: string;
	readonly signalId?: string;
	readonly status: "approved";
};

export type PostAgentFindingRejectResponse = {
	readonly findingId: string;
	readonly status: "rejected";
};

/** Agent 工具追踪 */
export type AgentToolCall = {
	readonly tool: string;
	readonly input: unknown;
	readonly output: unknown;
	readonly duration: number;
	readonly timestamp: string;
};

export type GetAgentFindingTraceResponse = {
	readonly finding: AgentFinding;
	readonly toolCalls: readonly AgentToolCall[];
	readonly reasoning: readonly string[];
};
