import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

type VersionDTO = components["schemas"]["ETFAllocationVersionResponse"];
type SaveBody = components["schemas"]["ETFAllocationBody"];
type ReviewDTO = components["schemas"]["ETFAllocationReviewResponse"];

export type ETFAllocationReviewView = {
	readonly valuationSnapshotId: string;
	readonly ledgerHash: string;
	readonly targetCashWeight: string;
	readonly actualCashWeight: string;
	readonly cashDriftBps: string;
	readonly positions: readonly {
		readonly instrumentId: number;
		readonly targetWeight: string;
		readonly actualWeight: string;
		readonly driftBps: string;
	}[];
	readonly actualExposure: Readonly<Record<string, string>>;
	readonly unknownExposureInstrumentIds: readonly number[];
};

export type ETFAllocationVersion = {
	readonly versionId: string;
	readonly allocationId: string;
	readonly parentVersionId: string | null;
	readonly asof: string;
	readonly knowledgeCutoff: string;
	readonly sourceSnapshotId: string;
	readonly mode: string;
	readonly weights: Readonly<Record<string, string>>;
	readonly cashWeight: string;
	readonly maxPositionWeight: string;
	readonly trackingExposure: Readonly<Record<string, string>>;
	readonly reason: string;
	readonly ruleVersion: string;
	readonly reviewStatus: string;
	readonly createdAt: string;
};

export type ETFPaperExecutionOutcome = {
	readonly intentId: string;
	readonly instrumentId: number;
	readonly status: string;
	readonly reason: string | null;
	readonly executionId: string | null;
	readonly ledgerEventId: string | null;
};

function toVersion(value: VersionDTO): ETFAllocationVersion {
	if (
		!value.version_id ||
		!value.allocation_id ||
		value.paper_status !== "research_only" ||
		!["research_only", "review_pending", "review_approved", "rejected"].includes(value.review_status)
	) {
		throw new Error("ETF 配置版本身份或审查状态无效");
	}
	return {
		versionId: value.version_id,
		allocationId: value.allocation_id,
		parentVersionId: value.parent_version_id,
		asof: value.asof,
		knowledgeCutoff: value.knowledge_cutoff,
		sourceSnapshotId: value.source_snapshot_id,
		mode: value.mode,
		weights: value.weights,
		cashWeight: value.cash_weight,
		maxPositionWeight: value.max_position_weight,
		trackingExposure: value.tracking_exposure,
		reason: value.reason,
		ruleVersion: value.rule_version,
		reviewStatus: value.review_status,
		createdAt: value.created_at,
	};
}

export async function listETFAllocationVersions(allocationId: string): Promise<ETFAllocationVersion[]> {
	const result = await apiClient.get("/api/v1/portfolio/etf-allocations/{allocation_id}/versions", {
		params: { path: { allocation_id: allocationId } },
	});
	const versions = result.map(toVersion);
	if (versions.some((version) => version.allocationId !== allocationId)) {
		throw new Error("ETF 配置版本响应不属于该配置");
	}
	return versions;
}

export async function fetchETFAllocationReview(
	allocationId: string,
	versionId: string,
	query: {
		account_kind: "paper" | "manual";
		account_id: string;
		as_of: string;
		knowledge_cutoff: string;
		source_snapshot_ids: string[];
	},
): Promise<ETFAllocationReviewView> {
	const result: ReviewDTO = await apiClient.get(
		"/api/v1/portfolio/etf-allocations/{allocation_id}/versions/{version_id}/review",
		{
			params: { path: { allocation_id: allocationId, version_id: versionId }, query },
		},
	);
	if (
		result.allocation_id !== allocationId ||
		result.version_id !== versionId ||
		result.account_kind !== query.account_kind ||
		result.account_id !== query.account_id ||
		result.as_of !== query.as_of ||
		result.source_snapshot_ids.join("\0") !== query.source_snapshot_ids.join("\0") ||
		result.target.valuation_snapshot_id !== result.actual.valuation_snapshot_id
	)
		throw new Error("ETF 复盘响应证据身份不匹配");
	return {
		valuationSnapshotId: result.valuation_snapshot_id,
		ledgerHash: result.ledger_hash,
		targetCashWeight: result.target.cash_weight,
		actualCashWeight: result.actual.cash_weight,
		cashDriftBps: result.drift.cash_drift_bps,
		positions: result.drift.items.map((item) => ({
			instrumentId: item.instrument_id,
			targetWeight: item.baseline_weight,
			actualWeight: item.observed_weight,
			driftBps: item.drift_bps,
		})),
		actualExposure: result.actual_exposure,
		unknownExposureInstrumentIds: result.unknown_exposure_instrument_ids,
	};
}

export async function saveETFAllocationVersion(
	allocationId: string,
	key: string,
	body: SaveBody,
): Promise<ETFAllocationVersion> {
	const result = await apiClient.post("/api/v1/portfolio/etf-allocations/{allocation_id}/versions", {
		params: { path: { allocation_id: allocationId }, header: { "Idempotency-Key": key } },
		body,
	});
	const version = toVersion(result);
	if (version.allocationId !== allocationId) throw new Error("ETF 配置响应身份不匹配");
	return version;
}

export async function reviewETFAllocationVersion(
	allocationId: string,
	versionId: string,
	key: string,
	body: components["schemas"]["ETFAllocationReviewBody"],
): Promise<ETFAllocationVersion> {
	const result = await apiClient.post(
		"/api/v1/portfolio/etf-allocations/{allocation_id}/versions/{version_id}/review",
		{
			params: { path: { allocation_id: allocationId, version_id: versionId }, header: { "Idempotency-Key": key } },
			body,
		},
	);
	const version = toVersion(result);
	if (version.allocationId !== allocationId || version.versionId !== versionId) {
		throw new Error("ETF 审批响应版本不匹配");
	}
	return version;
}

export async function authorizeETFPaper(
	allocationId: string,
	versionId: string,
	key: string,
	body: components["schemas"]["ETFPaperAuthorizeBody"],
): Promise<string> {
	const result = await apiClient.post(
		"/api/v1/portfolio/etf-allocations/{allocation_id}/versions/{version_id}/paper-authorizations",
		{
			params: { path: { allocation_id: allocationId, version_id: versionId }, header: { "Idempotency-Key": key } },
			body,
		},
	);
	if (result.version_id !== versionId || !result.authorization_id.startsWith(`${versionId}:paper:`)) {
		throw new Error("ETF Paper 授权响应身份不匹配");
	}
	return result.authorization_id;
}

export async function handoffETFPaper(
	allocationId: string,
	versionId: string,
	key: string,
	body: components["schemas"]["ETFPaperHandoffBody"],
): Promise<{ accountId: string; sessionId: string }> {
	const result = await apiClient.post(
		"/api/v1/portfolio/etf-allocations/{allocation_id}/versions/{version_id}/paper-handoffs",
		{
			params: { path: { allocation_id: allocationId, version_id: versionId }, header: { "Idempotency-Key": key } },
			body,
		},
	);
	if (
		result.session.account_id !== body.account_id ||
		result.session.session_id !== body.session_id ||
		result.session.strategy_id !== `etf-allocation:${allocationId}` ||
		result.session.trade_date !== body.intended_trade_date ||
		result.session.status !== "running"
	) {
		throw new Error("ETF Paper 会话响应身份不匹配");
	}
	return { accountId: result.session.account_id, sessionId: result.session.session_id };
}

const EXECUTION_OUTCOME_STATUSES = ["filled", "deferred", "rejected", "no_rebalance"] as const;

function assertOutcomeIdentity(outcome: components["schemas"]["ETFPaperExecutionOutcomeResponse"]) {
	const hasExecution = outcome.execution_id !== null;
	const hasLedger = outcome.ledger_event_id !== null;
	const identityValid =
		outcome.status === "filled"
			? hasExecution && hasLedger
			: outcome.status === "deferred" || outcome.status === "rejected"
				? hasExecution && !hasLedger
				: !hasExecution && !hasLedger;
	if (!identityValid) {
		throw new Error("ETF Paper 执行状态与执行/账本身份不匹配");
	}
}

export async function executeETFPaper(
	allocationId: string,
	versionId: string,
	key: string,
	body: components["schemas"]["ETFPaperExecutionBody"],
): Promise<ETFPaperExecutionOutcome[]> {
	const result = await apiClient.post(
		"/api/v1/portfolio/etf-allocations/{allocation_id}/versions/{version_id}/paper-executions",
		{
			params: { path: { allocation_id: allocationId, version_id: versionId }, header: { "Idempotency-Key": key } },
			body,
		},
	);
	for (const outcome of result.outcomes) {
		if (
			!outcome.intent_id ||
			!EXECUTION_OUTCOME_STATUSES.includes(outcome.status as (typeof EXECUTION_OUTCOME_STATUSES)[number])
		) {
			throw new Error("ETF Paper 执行响应缺少意图或状态无效");
		}
		assertOutcomeIdentity(outcome);
	}
	return result.outcomes.map((outcome) => ({
		intentId: outcome.intent_id,
		instrumentId: outcome.instrument_id,
		status: outcome.status,
		reason: outcome.reason,
		executionId: outcome.execution_id,
		ledgerEventId: outcome.ledger_event_id,
	}));
}
