export type DataProductOperationsScope = {
	readonly datasetId: string;
	readonly tradeDate: string;
	readonly availableSources?: readonly string[];
};

export type RemediationItemView = {
	readonly datasetId: string;
	readonly fallbackSources: readonly string[];
	readonly itemId: string;
	readonly namespace: string;
	readonly reasons: readonly string[];
	readonly severity: string;
	readonly source: string;
	readonly suggestedActions: readonly string[];
	readonly tradeDate: string | null;
};

export type RemediationBacklogView = {
	readonly generatedAt: string;
	readonly items: readonly RemediationItemView[];
	readonly totalItems: number;
};

export type RemediationItemDetailView = {
	readonly approvalIntents: readonly {
		readonly action: string;
		readonly intentType: string;
		readonly method: string | null;
		readonly notes: string | null;
		readonly path: string | null;
		readonly requestTemplate: Readonly<Record<string, unknown>>;
		readonly requiredOperatorInputs: readonly string[];
	}[];
	readonly evidenceRequirements: readonly {
		readonly description: string;
		readonly requirementId: string;
		readonly source: string;
		readonly status: string;
	}[];
	readonly generatedAt: string;
	readonly item: RemediationItemView;
	readonly summary: string;
};

export type SourceHealthView = {
	readonly blockers: readonly string[];
	readonly datasetId: string;
	readonly defaultSource: string;
	readonly failoverFromDefault: boolean;
	readonly fallbackSources: readonly string[];
	readonly selectedFreshnessStatus: string;
	readonly selectedSource: string;
	readonly status: string;
	readonly sources: readonly {
		readonly freshnessAt: string | null;
		readonly freshnessStatus: string;
		readonly source: string;
		readonly supported: boolean;
	}[];
	readonly tradeDate: string;
};

export type SourceHealthSummaryView = {
	readonly attentionReasons: readonly { readonly count: number; readonly reason: string }[];
	readonly attentionRequiredCount: number;
	readonly failoverCount: number;
	readonly noFallbackSourceCount: number;
	readonly revokedPromotionCount: number;
	readonly totalReports: number;
};

export type FallbackPreviewView = {
	readonly approvalRequired: boolean;
	readonly blockers: readonly string[];
	readonly datasetId: string;
	readonly defaultSource: string;
	readonly executionAllowed: boolean;
	readonly fallbackSources: readonly string[];
	readonly namespace: string;
	readonly policyStatus: string;
	readonly reasonCodes: readonly string[];
	readonly recommendedActions: readonly string[];
	readonly recommendedSource: string | null;
	readonly selectedSource: string;
	readonly sourceSelectionStatus: string;
	readonly tradeDate: string;
};

export type FallbackSummaryView = {
	readonly approvalRequiredCount: number;
	readonly executionAllowedCount: number;
	readonly policyStatuses: readonly { readonly count: number; readonly status: string }[];
	readonly recommendedActions: readonly { readonly action: string; readonly count: number }[];
	readonly totalPreviews: number;
};

export type FallbackPolicyView = {
	readonly approvalRequired: boolean;
	readonly createdAt: string;
	readonly createdBy: string;
	readonly datasetId: string;
	readonly defaultSource: string;
	readonly executionAllowed: boolean;
	readonly authorityHash: string;
	readonly authorityPayload: Readonly<Record<string, unknown>>;
	readonly namespace: string;
	readonly policyId: string;
	readonly recommendedSource: string | null;
	readonly reasonCodes: readonly string[];
	readonly selectedSource: string;
	readonly status: string;
	readonly tradeDate: string;
};

export type PromotionReadinessView = {
	readonly active: boolean;
	readonly currentMaturity: string | null;
	readonly datasetId: string;
	readonly missingCriteria: readonly string[];
	readonly rejectedCriteria: readonly string[];
	readonly satisfiedCriteria: readonly string[];
	readonly status: string;
};

export type PromotionHistoryView = {
	readonly action: string;
	readonly actionAt: string | null;
	readonly actor: string;
	readonly evidenceUri: string | null;
	readonly nextMaturity: string;
	readonly notes: string | null;
	readonly previousMaturity: string;
	readonly revocationReason: string | null;
};

export type RemediationApprovalView = {
	readonly action: string;
	readonly approvalId: string;
	readonly authorityHash: string;
	readonly expiresAt: string;
	readonly intentType: string;
	readonly itemId: string;
	readonly method: string | null;
	readonly path: string | null;
	readonly requestPayload: Readonly<Record<string, unknown>>;
	readonly requestedAt: string;
	readonly requestedBy: string;
	readonly status: string;
};

export type RequestRemediationApprovalCommand = {
	readonly action: string;
	readonly intentType: string;
	readonly itemId: string;
	readonly method?: string | null;
	readonly notes?: string | null;
	readonly path?: string | null;
	readonly requestPayload?: Readonly<Record<string, unknown>>;
	readonly requestedBy: string;
};

export type DecideRemediationApprovalCommand = {
	readonly approvalId: string;
	readonly authorityHash: string;
	readonly decidedBy: string;
	readonly decision: "approved" | "rejected";
	readonly notes?: string | null;
};

export type ExecuteRemediationApprovalCommand = {
	readonly approvalId: string;
	readonly authorityHash: string;
	readonly executedBy: string;
	readonly notes?: string | null;
};

export type FallbackPolicyLifecycleAction = "approval" | "activation" | "retirement";

export type TransitionFallbackPolicyCommand = {
	readonly action: FallbackPolicyLifecycleAction;
	readonly actor: string;
	readonly authorityHash: string;
	readonly datasetId: string;
	readonly notes?: string | null;
	readonly policyId: string;
};

export type RevokePromotionCommand = {
	readonly datasetId: string;
	readonly notes?: string | null;
	readonly reason: "policy_regression" | "failed_revalidation" | "manual_override" | "evidence_invalidated";
	readonly revokedBy: string;
};
