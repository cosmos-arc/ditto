import { type ApiResponse, apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
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

type AgentCapabilityResponse = components["schemas"]["AgentCapabilityResponse"];
type AgentSessionResponse = components["schemas"]["AgentSessionResponse"];
type AgentRunResponse = components["schemas"]["AgentRunResponse"];
type AgentApprovalResponse = components["schemas"]["AgentApprovalResponse"];
type AgentCampaignResponse = components["schemas"]["AgentCampaignResponse"];
type AgentRunCreateRequest = components["schemas"]["AgentRunCreateRequest"];
type AgentSessionCreateRequest = components["schemas"]["AgentSessionCreateRequest"];
type AgentApprovalDecisionRequest = components["schemas"]["AgentApprovalDecisionRequest"];
type AgentCampaignCreateRequest = components["schemas"]["AgentCampaignCreateRequest"];
type AgentCampaignApproveRequest = components["schemas"]["AgentCampaignApproveRequest"];
type AgentCampaignCancelRequest = components["schemas"]["AgentCampaignCancelRequest"];
type AgentCampaignValidationResponse = components["schemas"]["AgentCampaignValidationResponse"];
type AgentDecisionOpinionResponse = components["schemas"]["AgentDecisionOpinionResponse"];

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

function pagination(envelope: ApiResponse<unknown>, itemCount: number): AgentPage<never>["pagination"] {
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

function canonicalize(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(canonicalize);
	if (typeof value !== "object" || value === null) return value;
	return Object.fromEntries(
		Object.entries(value)
			.sort(([left], [right]) => left.localeCompare(right))
			.map(([key, item]) => [key, canonicalize(item)]),
	);
}

export async function canonicalSha256(value: unknown): Promise<string> {
	const bytes = new TextEncoder().encode(JSON.stringify(canonicalize(value)));
	const digest = await crypto.subtle.digest("SHA-256", bytes);
	return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function fetchAgentCapability(): Promise<AgentCapabilityView> {
	const response = await apiClient.get<AgentCapabilityResponse>("/v1/agent/capabilities");
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
	const envelope = await apiClient.getResponse<readonly AgentSessionResponse[]>(
		withQueryParams("/v1/agent/sessions", { limit, offset }),
	);
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
	const envelope = await apiClient.getResponse<readonly AgentRunResponse[]>(
		withQueryParams("/v1/agent/runs", {
			status: filters.status,
			session_id: filters.sessionId,
			context_type: filters.contextType,
			context_id: filters.contextId,
			limit: filters.limit ?? DEFAULT_PAGE_SIZE,
			offset: filters.offset ?? 0,
		}),
	);
	return { items: envelope.data.map(mapAgentRun), pagination: pagination(envelope, envelope.data.length) };
}

export async function getAgentRun(runId: string): Promise<AgentRunView> {
	return mapAgentRun(await apiClient.get<AgentRunResponse>(`/v1/agent/runs/${encodeURIComponent(runId)}`));
}

export async function listAgentApprovals(filters: AgentApprovalFilters = {}): Promise<AgentPage<AgentApprovalView>> {
	const envelope = await apiClient.getResponse<readonly AgentApprovalResponse[]>(
		withQueryParams("/v1/agent/approvals", {
			status: filters.status,
			run_id: filters.runId,
			limit: filters.limit ?? DEFAULT_PAGE_SIZE,
			offset: filters.offset ?? 0,
		}),
	);
	return { items: envelope.data.map(mapApproval), pagination: pagination(envelope, envelope.data.length) };
}

export async function getAgentApproval(approvalId: string): Promise<AgentApprovalView> {
	return mapApproval(
		await apiClient.get<AgentApprovalResponse>(`/v1/agent/approvals/${encodeURIComponent(approvalId)}`),
	);
}

export async function listAgentCampaigns(filters: AgentCampaignFilters = {}): Promise<AgentPage<AgentCampaignView>> {
	const envelope = await apiClient.getResponse<readonly AgentCampaignResponse[]>(
		withQueryParams("/v1/agent/campaigns", {
			status: filters.status,
			limit: filters.limit ?? DEFAULT_PAGE_SIZE,
			offset: filters.offset ?? 0,
		}),
	);
	return { items: envelope.data.map(mapCampaign), pagination: pagination(envelope, envelope.data.length) };
}

export async function getAgentCampaign(campaignId: string): Promise<AgentCampaignView> {
	return mapCampaign(
		await apiClient.get<AgentCampaignResponse>(`/v1/agent/campaigns/${encodeURIComponent(campaignId)}`),
	);
}

export async function createAgentSession(
	retentionClass: AgentSessionView["retentionClass"],
	idempotencyKey: string,
): Promise<AgentSessionView> {
	const payload: AgentSessionCreateRequest = { retention_class: retentionClass };
	const response = await apiClient.post<AgentSessionResponse>("/v1/agent/sessions", payload, {
		headers: { "Idempotency-Key": idempotencyKey },
	});
	return { sessionId: response.session_id, createdAt: response.created_at, retentionClass: response.retention_class };
}

export async function createAgentRun(input: CreateAgentRunInput): Promise<AgentRunView> {
	const authorityPayload = {
		context: input.context ? { context_id: input.context.contextId, context_type: input.context.contextType } : null,
		max_model_spend_usd: input.maxModelSpendUsd,
		max_model_tokens: input.maxModelTokens,
		model_profile: input.modelProfile,
		objective: input.objective,
		session_id: input.sessionId,
	};
	const payload: AgentRunCreateRequest = {
		...authorityPayload,
		authority_hash: await canonicalSha256(authorityPayload),
	};
	return mapAgentRun(
		await apiClient.post<AgentRunResponse>("/v1/agent/runs", payload, {
			headers: { "Idempotency-Key": input.idempotencyKey },
		}),
	);
}

export async function cancelAgentRun(run: Pick<AgentRunView, "runId" | "revision">): Promise<AgentRunView> {
	return mapAgentRun(
		await apiClient.post<AgentRunResponse>(`/v1/agent/runs/${encodeURIComponent(run.runId)}/cancel`, {
			expected_revision: run.revision,
		}),
	);
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
		reason: command.reason,
	};
	await apiClient.post(`/v1/agent/approvals/${encodeURIComponent(command.approvalId)}/decision`, payload);
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

function campaignValidationPayload(input: AgentCampaignValidationInput): object {
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
	const response = await apiClient.post<AgentCampaignValidationResponse>(
		"/v1/agent/campaigns/validation",
		campaignValidationPayload(input),
	);
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
		await apiClient.post<AgentCampaignResponse>("/v1/agent/campaigns", payload, {
			headers: { "Idempotency-Key": idempotencyKey },
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
		await apiClient.post<AgentCampaignResponse>(
			`/v1/agent/campaigns/${encodeURIComponent(command.campaignId)}/approve`,
			payload,
			{ headers: { "Idempotency-Key": command.idempotencyKey } },
		),
	);
}

export async function cancelAgentCampaign(command: {
	readonly campaignId: string;
	readonly authorizationHash: string;
	readonly idempotencyKey: string;
}): Promise<AgentCampaignView> {
	const payload: AgentCampaignCancelRequest = { expected_authorization_hash: command.authorizationHash };
	return mapCampaign(
		await apiClient.post<AgentCampaignResponse>(
			`/v1/agent/campaigns/${encodeURIComponent(command.campaignId)}/cancel`,
			payload,
			{ headers: { "Idempotency-Key": command.idempotencyKey } },
		),
	);
}

export async function fetchDecisionOpinion(identity: AgentDecisionOpinionIdentity): Promise<AgentDecisionOpinionView> {
	const response = await apiClient.get<AgentDecisionOpinionResponse>(
		withQueryParams("/v1/agent/decision-opinions", {
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
		}),
	);
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
