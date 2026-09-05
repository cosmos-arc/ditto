import { apiClient } from "@/api";
import {
	assertAgentApproval,
	assertAgentApprovalDecision,
	assertAgentApprovalList,
	assertAgentRun,
	assertAgentRunList,
} from "@/api/agent-validation";
import type { components } from "@/api/generated/schema";
import type {
	AgentApprovalFilters,
	AgentApprovalView,
	AgentCampaignFilters,
	AgentCampaignManifestInput,
	AgentCampaignValidationInput,
	AgentCampaignValidationView,
	AgentCampaignView,
	AgentCapabilityView,
	AgentDecisionOpinionIdentity,
	AgentDecisionOpinionView,
	AgentPage,
	AgentRunFilters,
	AgentRunView,
	AgentSessionView,
	AgentToolRecordView,
	CreateAgentRunInput,
} from "../types";

export type AgentCapabilityResponse = components["schemas"]["AgentCapabilityResponse"];
export type AgentSessionResponse = components["schemas"]["AgentSessionResponse"];
export type AgentRunResponse = components["schemas"]["AgentRunResponse"];
export type AgentApprovalResponse = components["schemas"]["AgentApprovalResponse"];
export type AgentCampaignResponse = components["schemas"]["AgentCampaignResponse"];
type AgentRunCreateRequest = components["schemas"]["AgentRunCreateRequest"];
type AgentRunExecuteRequest = components["schemas"]["AgentRunExecuteRequest"];
type AgentSessionCreateRequest = components["schemas"]["AgentSessionCreateRequest"];
type AgentApprovalDecisionRequest = components["schemas"]["AgentApprovalDecisionRequest"];
type AgentCampaignCreateRequest = components["schemas"]["AgentCampaignCreateRequest"];
type AgentCampaignApproveRequest = components["schemas"]["AgentCampaignApproveRequest"];
type AgentCampaignCancelRequest = components["schemas"]["AgentCampaignCancelRequest"];
type AgentCampaignValidationRequest =
	| components["schemas"]["AgentCampaignHypothesisValidationRequest"]
	| components["schemas"]["AgentCampaignExperimentPlanValidationRequest"]
	| components["schemas"]["AgentCampaignGovernanceValidationRequest"]
	| components["schemas"]["AgentCampaignManifestValidationRequest"];

const DEFAULT_PAGE_SIZE = 20;

export const agentQueryKeys = {
	all: ["agent"] as const,
	capability: () => [...agentQueryKeys.all, "capability"] as const,
	sessions: (offset: number) => [...agentQueryKeys.all, "sessions", offset] as const,
	runs: (filters: AgentRunFilters) => [...agentQueryKeys.all, "runs", filters] as const,
	run: (runId: string) => [...agentQueryKeys.all, "run", runId] as const,
	approvals: (filters: AgentApprovalFilters) => [...agentQueryKeys.all, "approvals", filters] as const,
	approval: (approvalId: string) => [...agentQueryKeys.all, "approval", approvalId] as const,
	campaigns: (filters: AgentCampaignFilters) => [...agentQueryKeys.all, "campaigns", filters] as const,
	campaign: (campaignId: string) => [...agentQueryKeys.all, "campaign", campaignId] as const,
	opinion: (identity: AgentDecisionOpinionIdentity) => [...agentQueryKeys.all, "decision-opinion", identity] as const,
};

type PaginatedEnvelope = {
	readonly pagination?: {
		readonly limit?: number;
		readonly offset?: number;
		readonly total?: number;
		readonly has_more?: boolean;
	} | null;
};

function pagination(envelope: PaginatedEnvelope, itemCount: number): AgentPage<never>["pagination"] {
	const value = envelope.pagination;
	const limit = value?.limit ?? Math.max(itemCount, DEFAULT_PAGE_SIZE);
	const offset = value?.offset ?? 0;
	const total = value?.total ?? itemCount;
	return {
		total,
		limit,
		offset,
		hasMore: value?.has_more ?? offset + itemCount < total,
	};
}

function mapToolRecord(record: components["schemas"]["AgentRunToolRecord"]): AgentToolRecordView {
	return {
		callId: record.call_id,
		toolName: record.tool_name,
		argumentsHash: record.arguments_hash,
		resultHash: record.result_hash,
		evidenceRefs: record.evidence_refs,
		artifactRefs: record.artifact_refs,
	};
}

export function mapAgentRun(response: AgentRunResponse): AgentRunView {
	return {
		runId: response.run_id,
		sessionId: response.session_id,
		status: response.status,
		objectiveHash: response.objective_hash,
		authorityHash: response.authority_hash,
		maxModelTokens: response.max_model_tokens,
		maxModelSpendUsd: response.max_model_spend_usd,
		modelProfile: response.model_profile,
		manifestHash: response.manifest_hash,
		createdAt: response.created_at,
		startedAt: response.started_at,
		finishedAt: response.finished_at,
		revision: response.revision,
		objective: response.objective,
		context: response.context
			? { contextType: response.context.context_type, contextId: response.context.context_id }
			: null,
		outputSummary: response.output_summary,
		toolRecords: response.tool_records.map(mapToolRecord),
		evidenceRefs: response.evidence_refs,
		artifactRefs: response.artifact_refs,
		guardrail: response.guardrail
			? { status: response.guardrail.status, reasonCode: response.guardrail.reason_code }
			: null,
		usage: response.usage
			? {
					modelAttempts: response.usage.model_attempts,
					modelTurns: response.usage.model_turns,
					toolCalls: response.usage.tool_calls,
					retries: response.usage.retries,
					totalTokens: response.usage.total_tokens,
					modelSpendUsd: response.usage.model_spend_usd,
					exhaustedReason: response.usage.exhausted_reason,
				}
			: null,
		failureCode: response.failure_code,
		executionPlan: response.execution_plan
			? {
					allowedTools: response.execution_plan.allowed_tools,
					allowedUniverse: response.execution_plan.allowed_universe,
					authorityHash: response.execution_plan.authority_hash,
					decisionTime: response.execution_plan.decision_time,
					egressClass: response.execution_plan.egress_class,
					executionEligibleAt: response.execution_plan.execution_eligible_at,
					knowledgeCutoff: response.execution_plan.knowledge_cutoff,
					licenseClass: response.execution_plan.license_class,
					maxOutputTokens: response.execution_plan.max_output_tokens,
					publicationCutoff: response.execution_plan.publication_cutoff,
					sourceSnapshotId: response.execution_plan.source_snapshot_id,
				}
			: null,
		eventCursor: response.event_cursor,
		projectionState: response.projection_state,
		projectionReason: response.projection_reason,
		projectionVersion: response.projection_version,
		projectionUpdatedAt: response.projection_updated_at,
	};
}

function mapApproval(response: AgentApprovalResponse): AgentApprovalView {
	return {
		approvalId: response.approval_id,
		runId: response.run_id,
		actionType: response.action_type,
		targetIdentity: response.target_identity,
		actionPayload: response.action_payload,
		actionHash: response.action_hash,
		status: response.status,
		requestedAt: response.requested_at,
		expiresAt: response.expires_at,
		operatorId: response.operator_id,
		reason: response.reason,
		decidedAt: response.decided_at,
	};
}

function mapCampaign(response: AgentCampaignResponse): AgentCampaignView {
	const sandbox = response.budget.sandbox_resource_limits;
	return {
		campaignId: response.campaign_id,
		status: response.status,
		canonicalManifest: response.canonical_manifest,
		manifestHash: response.manifest_hash,
		authorizationHash: response.authorization_hash,
		authorizedBy: response.authorized_by,
		authorizationExpiresAt: response.authorization_expires_at,
		searchAxis: response.search_axis,
		sourceSnapshotId: response.source_snapshot_id,
		allowedTools: response.allowed_tools,
		budget: {
			candidateLimit: response.budget.candidate_limit,
			foldRunLimit: response.budget.fold_run_limit,
			generationLimit: response.budget.generation_limit,
			concurrentSandboxLimit: response.budget.concurrent_sandbox_limit,
			wallTimeLimitSeconds: response.budget.wall_time_limit_seconds,
			temporaryStorageLimitBytes: response.budget.temporary_storage_limit_bytes,
			modelSpendLimitUsdMicros: response.budget.model_spend_limit_usd_micros,
			sandboxResourceLimits: {
				cpuCount: sandbox.cpu_count,
				memoryBytes: sandbox.memory_bytes,
				processLimit: sandbox.process_limit,
				temporaryStorageBytes: sandbox.temporary_storage_bytes,
				wallTimeSeconds: sandbox.wall_time_seconds,
				outputBytes: sandbox.output_bytes,
			},
		},
		bestPrimaryMetricValue: response.best_primary_metric_value,
		noImprovementGenerations: response.no_improvement_generations,
		statisticalTrialCount: response.statistical_trial_count,
		operationalAttemptCount: response.operational_attempt_count,
		revision: response.revision,
		objective: response.objective,
		outputSummary: response.output_summary,
		toolRecords: response.tool_records.map(mapToolRecord),
		evidenceRefs: response.evidence_refs,
		artifactRefs: response.artifact_refs,
		guardrail: response.guardrail
			? { status: response.guardrail.status, reasonCode: response.guardrail.reason_code }
			: null,
		usage: response.usage
			? {
					statisticalTrialCount: response.usage.statistical_trial_count,
					operationalAttemptCount: response.usage.operational_attempt_count,
					noImprovementGenerations: response.usage.no_improvement_generations,
					modelSpendUsdMicros: response.usage.model_spend_usd_micros,
					exhaustedReason: response.usage.exhausted_reason,
				}
			: null,
		eventCursor: response.event_cursor,
		projectionState: response.projection_state,
		projectionReason: response.projection_reason,
		projectionVersion: response.projection_version,
		projectionUpdatedAt: response.projection_updated_at,
	};
}

export async function fetchAgentCapability(): Promise<AgentCapabilityView> {
	const response = await apiClient.get("/api/v1/agent/capabilities");
	return {
		enabled: response.enabled,
		runtimeState: response.runtime_state,
		provider: response.provider,
		availableProfiles: response.available_profiles,
		defaultProfile: response.default_profile,
		degradationReason: response.degradation_reason,
		checkedAt: response.checked_at,
	};
}

export async function listAgentSessions(offset = 0, limit = DEFAULT_PAGE_SIZE): Promise<AgentPage<AgentSessionView>> {
	const envelope = await apiClient.getPayload("/api/v1/agent/sessions", { params: { query: { limit, offset } } });
	return {
		items: envelope.data.map((item) => ({
			sessionId: item.session_id,
			createdAt: item.created_at,
			retentionClass: item.retention_class,
		})),
		pagination: pagination(envelope, envelope.data.length),
	};
}

export async function listAgentRuns(filters: AgentRunFilters = {}): Promise<AgentPage<AgentRunView>> {
	const envelope = await apiClient.getPayload("/api/v1/agent/runs", {
		params: {
			query: {
				...(filters.status ? { status: filters.status } : {}),
				...(filters.sessionId ? { session_id: filters.sessionId } : {}),
				...(filters.contextType ? { context_type: filters.contextType } : {}),
				...(filters.contextId ? { context_id: filters.contextId } : {}),
				limit: filters.limit ?? DEFAULT_PAGE_SIZE,
				offset: filters.offset ?? 0,
			},
		},
	});
	assertAgentRunList(envelope.data);
	return { items: envelope.data.map(mapAgentRun), pagination: pagination(envelope, envelope.data.length) };
}

export async function getAgentRun(runId: string): Promise<AgentRunView> {
	const run = await apiClient.get("/api/v1/agent/runs/{run_id}", { params: { path: { run_id: runId } } });
	assertAgentRun(run);
	return mapAgentRun(run);
}

export async function listAgentApprovals(filters: AgentApprovalFilters = {}): Promise<AgentPage<AgentApprovalView>> {
	const envelope = await apiClient.getPayload("/api/v1/agent/approvals", {
		params: {
			query: {
				...(filters.status ? { status: filters.status } : {}),
				...(filters.runId ? { run_id: filters.runId } : {}),
				limit: filters.limit ?? DEFAULT_PAGE_SIZE,
				offset: filters.offset ?? 0,
			},
		},
	});
	assertAgentApprovalList(envelope.data);
	return { items: envelope.data.map(mapApproval), pagination: pagination(envelope, envelope.data.length) };
}

export async function getAgentApproval(approvalId: string): Promise<AgentApprovalView> {
	const approval = await apiClient.get("/api/v1/agent/approvals/{approval_id}", {
		params: { path: { approval_id: approvalId } },
	});
	assertAgentApproval(approval);
	return mapApproval(approval);
}

export async function listAgentCampaigns(filters: AgentCampaignFilters = {}): Promise<AgentPage<AgentCampaignView>> {
	const envelope = await apiClient.getPayload("/api/v1/agent/campaigns", {
		params: {
			query: {
				...(filters.status ? { status: filters.status } : {}),
				limit: filters.limit ?? DEFAULT_PAGE_SIZE,
				offset: filters.offset ?? 0,
			},
		},
	});
	return { items: envelope.data.map(mapCampaign), pagination: pagination(envelope, envelope.data.length) };
}

export async function getAgentCampaign(campaignId: string): Promise<AgentCampaignView> {
	return mapCampaign(
		await apiClient.get("/api/v1/agent/campaigns/{campaign_id}", {
			params: { path: { campaign_id: campaignId } },
		}),
	);
}

export async function createAgentSession(
	retentionClass: AgentSessionView["retentionClass"],
	idempotencyKey: string,
): Promise<AgentSessionView> {
	const payload: AgentSessionCreateRequest = { retention_class: retentionClass };
	const response = await apiClient.post("/api/v1/agent/sessions", {
		body: payload,
		params: { header: { "Idempotency-Key": idempotencyKey } },
	});
	return { sessionId: response.session_id, createdAt: response.created_at, retentionClass: response.retention_class };
}

export async function createAgentRun(input: CreateAgentRunInput): Promise<AgentRunView> {
	const payload: AgentRunCreateRequest = {
		context: input.context ? { context_id: input.context.contextId, context_type: input.context.contextType } : null,
		execution_scope: {
			allowed_universe: [...input.executionScope.allowedUniverse],
			decision_time: input.executionScope.decisionTime,
			knowledge_cutoff: input.executionScope.knowledgeCutoff,
			max_output_tokens: input.executionScope.maxOutputTokens,
			publication_cutoff: input.executionScope.publicationCutoff,
			source_snapshot_id: input.executionScope.sourceSnapshotId,
		},
		max_model_spend_usd: input.maxModelSpendUsd,
		max_model_tokens: input.maxModelTokens,
		model_profile: input.modelProfile,
		objective: input.objective,
		session_id: input.sessionId,
	};
	const run = await apiClient.post("/api/v1/agent/runs", {
		body: payload,
		params: { header: { "Idempotency-Key": input.idempotencyKey } },
	});
	assertAgentRun(run);
	return mapAgentRun(run);
}

export async function executeAgentRun(run: Pick<AgentRunView, "runId" | "revision">): Promise<AgentRunView> {
	const payload: AgentRunExecuteRequest = { expected_revision: run.revision };
	const response = await apiClient.post("/api/v1/agent/runs/{run_id}/execute", {
		body: payload,
		params: { path: { run_id: run.runId } },
	});
	assertAgentRun(response);
	return mapAgentRun(response);
}

export async function cancelAgentRun(run: Pick<AgentRunView, "runId" | "revision">): Promise<AgentRunView> {
	const response = await apiClient.post("/api/v1/agent/runs/{run_id}/cancel", {
		body: { expected_revision: run.revision },
		params: { path: { run_id: run.runId } },
	});
	assertAgentRun(response);
	return mapAgentRun(response);
}

export async function decideAgentApproval(command: {
	readonly approvalId: string;
	readonly actionHash: string;
	readonly decision: "approve" | "reject";
	readonly operatorId: string;
	readonly reason?: string | null;
}): Promise<void> {
	const payload: AgentApprovalDecisionRequest = {
		decision: command.decision,
		expected_action_hash: command.actionHash,
		operator_id: command.operatorId,
		...(command.reason === undefined ? {} : { reason: command.reason }),
	};
	const receipt = await apiClient.post("/api/v1/agent/approvals/{approval_id}/decision", {
		body: payload,
		params: { path: { approval_id: command.approvalId } },
	});
	assertAgentApprovalDecision(receipt);
}

function campaignManifest(input: AgentCampaignManifestInput): AgentCampaignCreateRequest["manifest"] {
	return {
		...input,
		allowed_tools: [...input.allowed_tools],
		prohibited_actions: [...input.prohibited_actions],
		baseline_candidate: {
			...input.baseline_candidate,
			parameters: { ...input.baseline_candidate.parameters },
			data_requirement_hashes: [...input.baseline_candidate.data_requirement_hashes],
		},
		budget: {
			...input.budget,
			sandbox_resource_limits: { ...input.budget.sandbox_resource_limits },
		},
		experiment_plan: { ...input.experiment_plan },
		hypothesis: { ...input.hypothesis },
	};
}

function campaignValidationPayload(input: AgentCampaignValidationInput): AgentCampaignValidationRequest {
	if (input.step === "hypothesis") {
		return { ...input, hypothesis: { ...input.hypothesis } };
	}
	if (input.step === "experiment_plan") {
		return {
			...input,
			baseline_candidate: {
				...input.baseline_candidate,
				parameters: { ...input.baseline_candidate.parameters },
				data_requirement_hashes: [...input.baseline_candidate.data_requirement_hashes],
			},
			experiment_plan: { ...input.experiment_plan },
		};
	}
	if (input.step === "governance") {
		return {
			...input,
			allowed_tools: [...input.allowed_tools],
			prohibited_actions: [...input.prohibited_actions],
			budget: {
				...input.budget,
				sandbox_resource_limits: { ...input.budget.sandbox_resource_limits },
			},
		};
	}
	return { step: "manifest", manifest: campaignManifest(input.manifest) };
}

export async function validateAgentCampaignStep(
	input: AgentCampaignValidationInput,
): Promise<AgentCampaignValidationView> {
	const response = await apiClient.post("/api/v1/agent/campaigns/validation", {
		body: campaignValidationPayload(input),
	});
	return {
		step: response.step,
		valid: response.valid,
		canonicalManifest: response.canonical_manifest,
		manifestHash: response.manifest_hash,
	};
}

export async function createAgentCampaign(
	manifest: AgentCampaignManifestInput,
	idempotencyKey: string,
): Promise<AgentCampaignView> {
	const payload: AgentCampaignCreateRequest = { manifest: campaignManifest(manifest) };
	return mapCampaign(
		await apiClient.post("/api/v1/agent/campaigns", {
			body: payload,
			params: { header: { "Idempotency-Key": idempotencyKey } },
		}),
	);
}

export async function approveAgentCampaign(command: {
	readonly campaignId: string;
	readonly manifestHash: string;
	readonly operatorId: string;
	readonly expiresAt: string;
	readonly idempotencyKey: string;
}): Promise<AgentCampaignView> {
	const payload: AgentCampaignApproveRequest = {
		expected_manifest_hash: command.manifestHash,
		operator_id: command.operatorId,
		expires_at: command.expiresAt,
	};
	return mapCampaign(
		await apiClient.post("/api/v1/agent/campaigns/{campaign_id}/approve", {
			body: payload,
			params: {
				path: { campaign_id: command.campaignId },
				header: { "Idempotency-Key": command.idempotencyKey },
			},
		}),
	);
}

export async function cancelAgentCampaign(command: {
	readonly campaignId: string;
	readonly authorizationHash: string;
	readonly idempotencyKey: string;
}): Promise<AgentCampaignView> {
	const payload: AgentCampaignCancelRequest = { expected_authorization_hash: command.authorizationHash };
	return mapCampaign(
		await apiClient.post("/api/v1/agent/campaigns/{campaign_id}/cancel", {
			body: payload,
			params: {
				path: { campaign_id: command.campaignId },
				header: { "Idempotency-Key": command.idempotencyKey },
			},
		}),
	);
}

export async function fetchDecisionOpinion(identity: AgentDecisionOpinionIdentity): Promise<AgentDecisionOpinionView> {
	const response = await apiClient.get("/api/v1/agent/decision-opinions", {
		params: {
			query: {
				strategy_id: identity.strategyId,
				strategy_version: identity.strategyVersion,
				trade_date: identity.tradeDate,
				account_id: identity.accountId,
				sleeve_id: identity.sleeveId,
				v3_artifact_id: identity.v3ArtifactId,
				decision_time: identity.decisionTime,
				knowledge_cutoff: identity.knowledgeCutoff,
				publication_cutoff: identity.publicationCutoff,
				source_snapshot_id: identity.sourceSnapshotId,
			},
		},
	});
	return {
		identity,
		status: response.status,
		generatedAt: response.generated_at,
		modelProfile: response.model_profile,
		summary: response.summary,
		disagreements: response.disagreements,
		uncertainties: response.uncertainties,
		evidenceRefs: response.evidence_refs,
		provenanceMatch: response.provenance_match,
		shadowOutcomeIdentity: response.shadow_outcome_identity,
		unavailableReason: response.unavailable_reason,
	};
}
