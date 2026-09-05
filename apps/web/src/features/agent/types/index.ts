export type AgentTab = "runs" | "campaigns" | "approvals";

export type AgentPagination = {
	readonly total: number;
	readonly limit: number;
	readonly offset: number;
	readonly hasMore: boolean;
};

export type AgentPage<T> = {
	readonly items: readonly T[];
	readonly pagination: AgentPagination;
};

export type AgentCapabilityView = {
	readonly enabled: boolean;
	readonly runtimeState: "available" | "degraded" | "disabled";
	readonly provider: string | null;
	readonly availableProfiles: readonly ("balanced" | "quality")[];
	readonly defaultProfile: "balanced" | "quality" | null;
	readonly degradationReason: string | null;
	readonly checkedAt: string;
};

export type AgentSessionView = {
	readonly sessionId: string;
	readonly createdAt: string;
	readonly retentionClass: "ephemeral" | "standard" | "audit";
};

export type AgentContextView = {
	readonly contextType: string;
	readonly contextId: string;
};

export type AgentToolRecordView = {
	readonly callId: string;
	readonly toolName: string;
	readonly argumentsHash: string;
	readonly resultHash: string;
	readonly evidenceRefs: readonly string[];
	readonly artifactRefs: readonly string[];
};

export type AgentGuardrailView = {
	readonly status: "passed" | "blocked" | "unknown";
	readonly reasonCode: string | null;
};

export type AgentRunUsageView = {
	readonly modelAttempts: number;
	readonly modelTurns: number;
	readonly toolCalls: number;
	readonly retries: number;
	readonly totalTokens: number;
	readonly modelSpendUsd: string;
	readonly exhaustedReason: string | null;
};

export type AgentRunExecutionScope = {
	readonly decisionTime: string;
	readonly knowledgeCutoff: string;
	readonly publicationCutoff: string;
	readonly sourceSnapshotId: string;
	readonly allowedUniverse: readonly string[];
	readonly maxOutputTokens: number;
};

export type AgentRunExecutionPlanView = AgentRunExecutionScope & {
	readonly allowedTools: readonly string[];
	readonly authorityHash: string;
	readonly licenseClass: string;
	readonly egressClass: "cloud_allowed";
	readonly executionEligibleAt: "not_applicable";
};

export type AgentRunStatus =
	| "queued"
	| "running"
	| "waiting_approval"
	| "paused"
	| "completed"
	| "failed"
	| "cancelled";

export type AgentRunView = {
	readonly runId: string;
	readonly sessionId: string;
	readonly status: AgentRunStatus;
	readonly objectiveHash: string;
	readonly authorityHash: string;
	readonly maxModelTokens: number;
	readonly maxModelSpendUsd: string;
	readonly modelProfile: "balanced" | "quality";
	readonly manifestHash: string;
	readonly createdAt: string;
	readonly startedAt: string | null;
	readonly finishedAt: string | null;
	readonly revision: number;
	readonly objective: string | null;
	readonly context: AgentContextView | null;
	readonly outputSummary: string | null;
	readonly toolRecords: readonly AgentToolRecordView[];
	readonly evidenceRefs: readonly string[];
	readonly artifactRefs: readonly string[];
	readonly guardrail: AgentGuardrailView | null;
	readonly usage: AgentRunUsageView | null;
	readonly failureCode: string | null;
	readonly executionPlan: AgentRunExecutionPlanView | null;
	readonly eventCursor: number;
	readonly projectionState: "complete" | "partial";
	readonly projectionReason: string | null;
	readonly projectionVersion: number | null;
	readonly projectionUpdatedAt: string | null;
};

export type AgentApprovalView = {
	readonly approvalId: string;
	readonly runId: string;
	readonly actionType: string;
	readonly targetIdentity: string;
	readonly actionPayload: Readonly<Record<string, unknown>>;
	readonly actionHash: string;
	readonly status: "pending" | "approved" | "rejected" | "expired";
	readonly requestedAt: string;
	readonly expiresAt: string;
	readonly operatorId: string | null;
	readonly reason: string | null;
	readonly decidedAt: string | null;
};

export type CampaignBudgetView = {
	readonly candidateLimit: number;
	readonly foldRunLimit: number;
	readonly generationLimit: number;
	readonly concurrentSandboxLimit: number;
	readonly wallTimeLimitSeconds: number;
	readonly temporaryStorageLimitBytes: number;
	readonly modelSpendLimitUsdMicros: number;
	readonly sandboxResourceLimits: {
		readonly cpuCount: number;
		readonly memoryBytes: number;
		readonly processLimit: number;
		readonly temporaryStorageBytes: number;
		readonly wallTimeSeconds: number;
		readonly outputBytes: number;
	};
};

export type AgentCampaignStatus =
	| "draft"
	| "authorized"
	| "running"
	| "paused"
	| "paused_budget"
	| "cancel_requested"
	| "cancelled"
	| "completed"
	| "completed_with_failures"
	| "failed";

export type AgentCampaignView = {
	readonly campaignId: string;
	readonly status: AgentCampaignStatus;
	readonly canonicalManifest: Readonly<Record<string, unknown>>;
	readonly manifestHash: string;
	readonly authorizationHash: string | null;
	readonly authorizedBy: string | null;
	readonly authorizationExpiresAt: string | null;
	readonly searchAxis: string;
	readonly sourceSnapshotId: string;
	readonly allowedTools: readonly string[];
	readonly budget: CampaignBudgetView;
	readonly bestPrimaryMetricValue: number | null;
	readonly noImprovementGenerations: number;
	readonly statisticalTrialCount: number;
	readonly operationalAttemptCount: number;
	readonly revision: number;
	readonly objective: string | null;
	readonly outputSummary: string | null;
	readonly toolRecords: readonly AgentToolRecordView[];
	readonly evidenceRefs: readonly string[];
	readonly artifactRefs: readonly string[];
	readonly guardrail: AgentGuardrailView | null;
	readonly usage: {
		readonly statisticalTrialCount: number;
		readonly operationalAttemptCount: number;
		readonly noImprovementGenerations: number;
		readonly modelSpendUsdMicros: number | null;
		readonly exhaustedReason: string | null;
	} | null;
	readonly eventCursor: number;
	readonly projectionState: "complete" | "partial";
	readonly projectionReason: string | null;
	readonly projectionVersion: number | null;
	readonly projectionUpdatedAt: string | null;
};

export type AgentRunFilters = {
	readonly status?: AgentRunStatus | undefined;
	readonly sessionId?: string | undefined;
	readonly contextType?: string | undefined;
	readonly contextId?: string | undefined;
	readonly limit?: number | undefined;
	readonly offset?: number | undefined;
};

export type AgentApprovalFilters = {
	readonly status?: AgentApprovalView["status"] | undefined;
	readonly runId?: string | undefined;
	readonly limit?: number | undefined;
	readonly offset?: number | undefined;
};

export type AgentCampaignFilters = {
	readonly status?: AgentCampaignStatus | undefined;
	readonly limit?: number | undefined;
	readonly offset?: number | undefined;
};

export type CreateAgentRunInput = {
	readonly sessionId: string;
	readonly objective: string;
	readonly maxModelTokens: number;
	readonly maxModelSpendUsd: string;
	readonly modelProfile: "balanced" | "quality";
	readonly context?: AgentContextView | null;
	readonly executionScope: AgentRunExecutionScope;
	readonly idempotencyKey: string;
};

export type AgentCampaignManifestInput = {
	readonly campaign_id: string;
	readonly objective: string;
	readonly primary_metric_id: string;
	readonly hypothesis: {
		readonly statement: string;
		readonly mechanism: string;
		readonly universe_hash: string;
		readonly expected_signal: string;
		readonly failure_condition: string;
	};
	readonly baseline_candidate: {
		readonly candidate_id: string;
		readonly ordinal: number;
		readonly parameters: Readonly<Record<string, unknown>>;
		readonly factor_code_hash?: string | null;
		readonly model_code_hash?: string | null;
		readonly data_requirement_hashes: readonly string[];
	};
	readonly experiment_plan: {
		readonly fold_protocol_id: string;
		readonly fold_protocol_version: number;
		readonly fold_protocol_hash: string;
		readonly snapshot_id: string;
		readonly validation_objective_hash: string;
		readonly cost_model_hash: string;
		readonly seed: number;
		readonly purge_sessions: number;
		readonly embargo_sessions: number;
	};
	readonly budget: {
		readonly candidate_limit: number;
		readonly fold_run_limit: number;
		readonly generation_limit: number;
		readonly concurrent_sandbox_limit: number;
		readonly wall_time_limit_seconds: number;
		readonly temporary_storage_limit_bytes: number;
		readonly model_spend_limit_usd_micros: number;
		readonly sandbox_resource_limits: {
			readonly cpu_count: number;
			readonly memory_bytes: number;
			readonly process_limit: number;
			readonly temporary_storage_bytes: number;
			readonly wall_time_seconds: number;
			readonly output_bytes: number;
		};
	};
	readonly search_axis: "factor_code" | "model_code" | "parameters";
	readonly search_space_hash: string;
	readonly lineage_root: string;
	readonly stopping_rule: string;
	readonly allowed_tools: readonly string[];
	readonly prohibited_actions: readonly string[];
};

export type AgentCampaignValidationInput =
	| {
			readonly step: "hypothesis";
			readonly campaign_id: string;
			readonly objective: string;
			readonly primary_metric_id: string;
			readonly hypothesis: AgentCampaignManifestInput["hypothesis"];
	  }
	| {
			readonly step: "experiment_plan";
			readonly search_axis: AgentCampaignManifestInput["search_axis"];
			readonly baseline_candidate: AgentCampaignManifestInput["baseline_candidate"];
			readonly experiment_plan: AgentCampaignManifestInput["experiment_plan"];
	  }
	| {
			readonly step: "governance";
			readonly budget: AgentCampaignManifestInput["budget"];
			readonly search_space_hash: string;
			readonly lineage_root: string;
			readonly stopping_rule: string;
			readonly allowed_tools: readonly string[];
			readonly prohibited_actions: readonly string[];
	  }
	| {
			readonly step: "manifest";
			readonly manifest: AgentCampaignManifestInput;
	  };

export type AgentCampaignValidationView = {
	readonly step: AgentCampaignValidationInput["step"];
	readonly valid: boolean;
	readonly canonicalManifest: Readonly<Record<string, unknown>> | null;
	readonly manifestHash: string | null;
};

export type AgentDecisionOpinionIdentity = {
	readonly strategyId: string;
	readonly strategyVersion: string;
	readonly tradeDate: string;
	readonly accountId: string;
	readonly sleeveId: string;
	readonly v3ArtifactId: string;
	readonly decisionTime: string;
	readonly knowledgeCutoff: string;
	readonly publicationCutoff: string;
	readonly sourceSnapshotId: string;
};

export type AgentDecisionOpinionView = {
	readonly identity: AgentDecisionOpinionIdentity;
	readonly status: "completed" | "blocked" | "unavailable";
	readonly generatedAt: string | null;
	readonly modelProfile: string | null;
	readonly summary: string | null;
	readonly disagreements: readonly string[];
	readonly uncertainties: readonly string[];
	readonly evidenceRefs: readonly string[];
	readonly provenanceMatch: boolean;
	readonly shadowOutcomeIdentity: string | null;
	readonly unavailableReason: string | null;
};
