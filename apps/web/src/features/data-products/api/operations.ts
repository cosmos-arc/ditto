import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";
import type {
	DataProductOperationsScope,
	DecideRemediationApprovalCommand,
	ExecuteRemediationApprovalCommand,
	FallbackPolicyView,
	FallbackPreviewView,
	FallbackSummaryView,
	PromotionHistoryView,
	PromotionReadinessView,
	RemediationApprovalView,
	RemediationBacklogView,
	RemediationItemDetailView,
	RequestRemediationApprovalCommand,
	RevokePromotionCommand,
	SourceHealthSummaryView,
	SourceHealthView,
	TransitionFallbackPolicyCommand,
} from "../types/operations";

type CatalogRemediationBacklogResponse = components["schemas"]["CatalogRemediationBacklogResponse"];
type CatalogSourceFallbackPolicyStateResponse = components["schemas"]["CatalogSourceFallbackPolicyStateResponse"];
type CatalogRemediationApprovalResponse = components["schemas"]["CatalogRemediationApprovalResponse"];
type CatalogRemediationApprovalExecutionResponse = components["schemas"]["CatalogRemediationApprovalExecutionResponse"];
type CatalogSourceFallbackPolicyDraftRequest = components["schemas"]["CatalogSourceFallbackPolicyDraftRequest"];
type CatalogRemediationApprovalRequest = components["schemas"]["CatalogRemediationApprovalRequest"];
type CatalogRemediationApprovalDecisionRequest = components["schemas"]["CatalogRemediationApprovalDecisionRequest"];
type CatalogRemediationApprovalExecutionRequest = components["schemas"]["CatalogRemediationApprovalExecutionRequest"];
type CatalogSourceFallbackPolicyLifecycleRequest = components["schemas"]["CatalogSourceFallbackPolicyLifecycleRequest"];
type MaturityPromotionRevokeRequest = components["schemas"]["MaturityPromotionRevokeRequest"];
type MaturityPromotionRevokeResponse = components["schemas"]["MaturityPromotionRevokeResponse"];

export const dataProductOperationsKeys = {
	all: ["data-products", "operations"] as const,
	scope: (datasetId: string, tradeDate: string) => [...dataProductOperationsKeys.all, datasetId, tradeDate] as const,
	remediation: (datasetId: string, tradeDate: string) =>
		[...dataProductOperationsKeys.scope(datasetId, tradeDate), "remediation"] as const,
	remediationDetail: (datasetId: string, tradeDate: string, itemId: string) =>
		[...dataProductOperationsKeys.remediation(datasetId, tradeDate), "detail", itemId] as const,
	sourceHealth: (datasetId: string, tradeDate: string) =>
		[...dataProductOperationsKeys.scope(datasetId, tradeDate), "source-health"] as const,
	sourceHealthSummary: (datasetId: string, tradeDate: string) =>
		[...dataProductOperationsKeys.scope(datasetId, tradeDate), "source-health-summary"] as const,
	fallbackPreview: (datasetId: string, tradeDate: string) =>
		[...dataProductOperationsKeys.scope(datasetId, tradeDate), "fallback-preview"] as const,
	fallbackPolicies: (datasetId: string) => [...dataProductOperationsKeys.all, datasetId, "fallback-policies"] as const,
	fallbackSummary: (datasetId: string, tradeDate: string) =>
		[...dataProductOperationsKeys.scope(datasetId, tradeDate), "fallback-summary"] as const,
	promotion: (datasetId: string, tradeDate: string) =>
		[...dataProductOperationsKeys.scope(datasetId, tradeDate), "promotion"] as const,
	promotionHistory: (datasetId: string) => [...dataProductOperationsKeys.all, datasetId, "promotion-history"] as const,
	approvals: (datasetId: string) => [...dataProductOperationsKeys.all, datasetId, "remediation-approvals"] as const,
};

function pluralScopeQuery(scope: DataProductOperationsScope) {
	return {
		dataset_ids: [scope.datasetId],
		trade_dates: [scope.tradeDate],
		...(scope.availableSources ? { available_sources: [...scope.availableSources] } : {}),
	};
}

function singularScopeQuery(scope: DataProductOperationsScope) {
	return {
		dataset_id: scope.datasetId,
		trade_date: scope.tradeDate,
		...(scope.availableSources ? { available_sources: [...scope.availableSources] } : {}),
	};
}

function mapApproval(response: CatalogRemediationApprovalResponse): RemediationApprovalView {
	return {
		action: response.action,
		approvalId: response.approval_id,
		authorityHash: response.authority_hash,
		expiresAt: response.expires_at,
		intentType: response.intent_type,
		itemId: response.item_id,
		method: response.method ?? null,
		path: response.path ?? null,
		requestPayload: response.request_payload ?? {},
		requestedAt: response.requested_at,
		requestedBy: response.requested_by,
		status: response.status,
	};
}

function mapRemediationItem(
	item: CatalogRemediationBacklogResponse["items"][number],
): RemediationBacklogView["items"][number] {
	return {
		datasetId: item.dataset_id,
		fallbackSources: item.fallback_sources ?? [],
		itemId: item.item_id,
		namespace: item.namespace,
		reasons: item.reasons ?? [],
		severity: item.severity,
		source: item.source,
		suggestedActions: item.suggested_actions ?? [],
		tradeDate: item.trade_date ?? null,
	};
}

export async function fetchRemediationBacklog(scope: DataProductOperationsScope): Promise<RemediationBacklogView> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/remediation/backlog", {
		params: { query: pluralScopeQuery(scope) },
	});
	return {
		generatedAt: response.generated_at,
		totalItems: response.total_items,
		items: response.items.map(mapRemediationItem),
	};
}

export async function fetchRemediationDetail(
	itemId: string,
	scope: DataProductOperationsScope,
): Promise<RemediationItemDetailView> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/remediation/items/{item_id}", {
		params: { path: { item_id: itemId }, query: pluralScopeQuery(scope) },
	});
	return {
		approvalIntents: (response.approval_intents ?? []).map((intent) => ({
			action: intent.action,
			intentType: intent.intent_type,
			method: intent.method ?? null,
			notes: intent.notes ?? null,
			path: intent.path ?? null,
			requestTemplate: intent.request_template ?? {},
			requiredOperatorInputs: intent.required_operator_inputs ?? [],
		})),
		evidenceRequirements: (response.evidence_requirements ?? []).map((requirement) => ({
			description: requirement.description,
			requirementId: requirement.requirement_id,
			source: requirement.source,
			status: requirement.status,
		})),
		generatedAt: response.generated_at,
		item: mapRemediationItem(response.item),
		summary: response.summary,
	};
}

export async function fetchSourceHealth(scope: DataProductOperationsScope): Promise<SourceHealthView> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/source-health", {
		params: { query: singularScopeQuery(scope) },
	});
	return {
		blockers: response.source_selection_blockers ?? [],
		datasetId: response.dataset_id,
		defaultSource: response.default_source,
		failoverFromDefault: response.failover_from_default ?? response.selected_source !== response.default_source,
		fallbackSources: response.fallback_sources ?? [],
		selectedFreshnessStatus: response.selected_freshness_status,
		selectedSource: response.selected_source,
		status: response.source_selection_status,
		sources: response.sources.map((source) => ({
			freshnessAt: source.freshness_at ?? null,
			freshnessStatus: source.freshness_status,
			source: source.source,
			supported: source.supported,
		})),
		tradeDate: response.trade_date,
	};
}

export async function fetchSourceHealthSummary(scope: DataProductOperationsScope): Promise<SourceHealthSummaryView> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/source-health/summary", {
		params: { query: pluralScopeQuery(scope) },
	});
	return {
		attentionReasons: (response.attention_reason_counts ?? []).map((item) => ({
			count: item.count,
			reason: item.reason,
		})),
		attentionRequiredCount: response.attention_required.length,
		failoverCount: response.failover_count,
		noFallbackSourceCount: response.no_fallback_source_count,
		revokedPromotionCount: response.revoked_promotion_count,
		totalReports: response.total_reports,
	};
}

export async function fetchFallbackPreview(scope: DataProductOperationsScope): Promise<FallbackPreviewView> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/source-fallback/preview", {
		params: { query: singularScopeQuery(scope) },
	});
	return {
		approvalRequired: response.approval_required,
		blockers: response.source_selection_blockers ?? [],
		datasetId: response.dataset_id,
		defaultSource: response.default_source,
		executionAllowed: response.execution_allowed,
		fallbackSources: response.fallback_sources ?? [],
		namespace: response.namespace,
		policyStatus: response.policy_status,
		reasonCodes: response.reason_codes ?? [],
		recommendedActions: response.recommended_actions ?? [],
		recommendedSource: response.recommended_source ?? null,
		selectedSource: response.selected_source,
		sourceSelectionStatus: response.source_selection_status,
		tradeDate: response.trade_date,
	};
}

export async function fetchFallbackPolicies(datasetId: string): Promise<readonly FallbackPolicyView[]> {
	const responses = await apiClient.get("/api/v1/ingestion/catalog/source-fallback/policies", {
		params: { query: { dataset_id: datasetId } },
	});
	return responses.map((response) => ({
		approvalRequired: response.approval_required,
		authorityHash: response.authority_hash,
		authorityPayload: response.authority_payload,
		createdAt: response.created_at,
		createdBy: response.created_by,
		datasetId: response.dataset_id,
		defaultSource: response.default_source,
		executionAllowed: response.execution_allowed,
		namespace: response.namespace,
		policyId: response.policy_id,
		recommendedSource: response.recommended_source ?? null,
		reasonCodes: response.reason_codes ?? [],
		selectedSource: response.selected_source,
		status: response.status,
		tradeDate: response.trade_date,
	}));
}

export async function fetchFallbackSummary(scope: DataProductOperationsScope): Promise<FallbackSummaryView> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/source-fallback/summary", {
		params: { query: pluralScopeQuery(scope) },
	});
	return {
		approvalRequiredCount: response.approval_required_count,
		executionAllowedCount: response.execution_allowed_count,
		policyStatuses: response.policy_status_counts.map((item) => ({ count: item.count, status: item.status })),
		recommendedActions: (response.recommended_action_counts ?? []).map((item) => ({
			action: item.action,
			count: item.count,
		})),
		totalPreviews: response.total_previews,
	};
}

export async function fetchPromotionReadiness(
	scope: DataProductOperationsScope,
): Promise<PromotionReadinessView | null> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/promotion/readiness", {
		params: { query: pluralScopeQuery(scope) },
	});
	const item = response.datasets.find((candidate) => candidate.dataset_id === scope.datasetId);
	return item
		? {
				active: item.active_maturity_promotion,
				currentMaturity: item.current_maturity ?? null,
				datasetId: item.dataset_id,
				missingCriteria: item.missing_criteria ?? [],
				rejectedCriteria: item.rejected_criteria ?? [],
				satisfiedCriteria: item.satisfied_criteria ?? [],
				status: item.promotion_status,
			}
		: null;
}

export async function fetchPromotionHistory(datasetId: string): Promise<readonly PromotionHistoryView[]> {
	const responses = await apiClient.get("/api/v1/ingestion/catalog/promotion/history", {
		params: { query: { dataset_id: datasetId } },
	});
	return responses.map((item) => ({
		action: item.action,
		actionAt: item.action_at ?? null,
		actor: item.actor,
		evidenceUri: item.evidence_uri ?? null,
		nextMaturity: item.next_maturity,
		notes: item.notes ?? null,
		previousMaturity: item.previous_maturity,
		revocationReason: item.revocation_reason ?? null,
	}));
}

export async function fetchRemediationApprovals(datasetId: string): Promise<readonly RemediationApprovalView[]> {
	const responses = await apiClient.get("/api/v1/ingestion/catalog/remediation/approvals");
	return responses.filter((response) => response.item_id.includes(datasetId)).map(mapApproval);
}

export async function requestRemediationApproval(
	command: RequestRemediationApprovalCommand,
): Promise<RemediationApprovalView> {
	const payload: CatalogRemediationApprovalRequest = {
		action: command.action,
		intent_type: command.intentType,
		item_id: command.itemId,
		...(command.method === undefined ? {} : { method: command.method }),
		...(command.notes === undefined ? {} : { notes: command.notes }),
		...(command.path === undefined ? {} : { path: command.path }),
		...(command.requestPayload === undefined ? {} : { request_payload: { ...command.requestPayload } }),
		requested_by: command.requestedBy,
	};
	return mapApproval(await apiClient.post("/api/v1/ingestion/catalog/remediation/approvals", { body: payload }));
}

export async function decideRemediationApproval(
	command: DecideRemediationApprovalCommand,
): Promise<RemediationApprovalView> {
	const payload: CatalogRemediationApprovalDecisionRequest = {
		authority_hash: command.authorityHash,
		decided_by: command.decidedBy,
		decision: command.decision,
		...(command.notes === undefined ? {} : { notes: command.notes }),
	};
	return mapApproval(
		await apiClient.post("/api/v1/ingestion/catalog/remediation/approvals/{approval_id}/decision", {
			body: payload,
			params: { path: { approval_id: command.approvalId } },
		}),
	);
}

export async function executeRemediationApproval(
	command: ExecuteRemediationApprovalCommand,
): Promise<CatalogRemediationApprovalExecutionResponse> {
	const payload: CatalogRemediationApprovalExecutionRequest = {
		authority_hash: command.authorityHash,
		executed_by: command.executedBy,
		...(command.notes === undefined ? {} : { notes: command.notes }),
	};
	return apiClient.post("/api/v1/ingestion/catalog/remediation/approvals/{approval_id}/execute", {
		body: payload,
		params: { path: { approval_id: command.approvalId } },
	});
}

export async function draftFallbackPolicy(
	preview: FallbackPreviewView,
	createdBy: string,
): Promise<CatalogSourceFallbackPolicyStateResponse> {
	const payload: CatalogSourceFallbackPolicyDraftRequest = {
		approval_required: preview.approvalRequired,
		created_by: createdBy,
		dataset_id: preview.datasetId,
		default_source: preview.defaultSource,
		execution_allowed: preview.executionAllowed,
		fallback_sources: [...preview.fallbackSources],
		namespace: preview.namespace,
		reason_codes: [...preview.reasonCodes],
		recommended_actions: [...preview.recommendedActions],
		recommended_source: preview.recommendedSource,
		selected_source: preview.selectedSource,
		source_selection_blockers: [...preview.blockers],
		source_selection_status: preview.sourceSelectionStatus,
		trade_date: preview.tradeDate,
		unsupported_sources: [],
	};
	return apiClient.post("/api/v1/ingestion/catalog/source-fallback/policies", { body: payload });
}

export async function transitionFallbackPolicy(
	command: TransitionFallbackPolicyCommand,
): Promise<CatalogSourceFallbackPolicyStateResponse> {
	const payload: CatalogSourceFallbackPolicyLifecycleRequest = {
		actor: command.actor,
		authority_hash: command.authorityHash,
		...(command.notes === undefined ? {} : { notes: command.notes }),
	};
	const init = { body: payload, params: { path: { policy_id: command.policyId } } };
	switch (command.action) {
		case "approval":
			return apiClient.post("/api/v1/ingestion/catalog/source-fallback/policies/{policy_id}/approval", init);
		case "activation":
			return apiClient.post("/api/v1/ingestion/catalog/source-fallback/policies/{policy_id}/activation", init);
		case "retirement":
			return apiClient.post("/api/v1/ingestion/catalog/source-fallback/policies/{policy_id}/retirement", init);
	}
}

export async function revokePromotion(command: RevokePromotionCommand): Promise<MaturityPromotionRevokeResponse> {
	const payload: MaturityPromotionRevokeRequest = {
		dataset_id: command.datasetId,
		...(command.notes === undefined ? {} : { notes: command.notes }),
		revocation_reason: command.reason,
		revoked_by: command.revokedBy,
	};
	return apiClient.post("/api/v1/ingestion/catalog/promotion/revoke", { body: payload });
}
