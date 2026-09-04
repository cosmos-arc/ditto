import { apiClient } from "@/lib/api-client";
import type { components, operations } from "@/types/generated/api";

export type PortfolioComparisonIdentity = operations["portfolio_get_comparison"]["parameters"]["query"];
export type PortfolioScenarioRequest = components["schemas"]["PortfolioScenarioBody"];
export type PortfolioComparison = components["schemas"]["PortfolioComparisonResponse"];
export type PortfolioScenarioPreview = components["schemas"]["PortfolioScenarioPreviewResponse"];

function comparisonUrl(identity: PortfolioComparisonIdentity): string {
	const search = new URLSearchParams();
	for (const [key, value] of Object.entries(identity)) {
		if (value == null || key === "source_snapshot_ids") continue;
		search.set(key, String(value));
	}
	for (const snapshotId of identity.source_snapshot_ids) {
		search.append("source_snapshot_ids", snapshotId);
	}
	return `/v1/portfolio/comparison?${search.toString()}`;
}

function sameSnapshotSet(left: readonly string[], right: readonly string[]): boolean {
	const sortedLeft = [...left].sort();
	const sortedRight = [...right].sort();
	return sortedLeft.length === sortedRight.length && sortedLeft.every((value, index) => value === sortedRight[index]);
}

function assertComparisonIdentity(identity: PortfolioComparisonIdentity, comparison: PortfolioComparison): void {
	if (comparison.strategy_id !== identity.strategy_id) throw new Error("comparison strategy_id mismatch");
	if (comparison.as_of !== identity.as_of) throw new Error("comparison as_of mismatch");
	if (!sameSnapshotSet(comparison.source_snapshot_ids, identity.source_snapshot_ids)) {
		throw new Error("comparison source snapshot mismatch");
	}
	if (identity.valuation_snapshot_id && comparison.valuation_snapshot_id !== identity.valuation_snapshot_id) {
		throw new Error("comparison valuation snapshot mismatch");
	}
}

export async function fetchPortfolioComparison(identity: PortfolioComparisonIdentity): Promise<PortfolioComparison> {
	const comparison = await apiClient.get<PortfolioComparison>(comparisonUrl(identity));
	assertComparisonIdentity(identity, comparison);
	return comparison;
}

export async function previewPortfolioScenario(request: PortfolioScenarioRequest): Promise<PortfolioScenarioPreview> {
	const preview = await apiClient.post<PortfolioScenarioPreview>("/v1/portfolio/scenario-previews", request);
	if (preview.baseline_kind !== request.baseline_kind) throw new Error("scenario baseline mismatch");
	if (preview.risk.as_of !== request.as_of) throw new Error("scenario as_of mismatch");
	if (!sameSnapshotSet(preview.risk.source_snapshot_ids, request.source_snapshot_ids)) {
		throw new Error("scenario source snapshot mismatch");
	}
	if (request.valuation_snapshot_id && preview.risk.valuation_snapshot_id !== request.valuation_snapshot_id) {
		throw new Error("scenario valuation snapshot mismatch");
	}
	return preview;
}
