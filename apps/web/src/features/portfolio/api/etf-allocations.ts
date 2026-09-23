import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

type VersionDTO = components["schemas"]["ETFAllocationVersionResponse"];
type SaveBody = components["schemas"]["ETFAllocationBody"];

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
	readonly paperStatus: string;
	readonly createdAt: string;
};

function toVersion(value: VersionDTO): ETFAllocationVersion {
	if (
		!value.version_id ||
		!value.allocation_id ||
		!["research_only", "review_pending", "review_approved", "rejected"].includes(value.paper_status)
	) {
		throw new Error("ETF 配置版本身份或审批状态无效");
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
		paperStatus: value.paper_status,
		createdAt: value.created_at,
	};
}

export async function listETFAllocationVersions(allocationId: string): Promise<ETFAllocationVersion[]> {
	const result = await apiClient.get("/api/v1/portfolio/etf-allocations/{allocation_id}/versions", {
		params: { path: { allocation_id: allocationId } },
	});
	return result.map(toVersion);
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
	return toVersion(result);
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
	return toVersion(result);
}
