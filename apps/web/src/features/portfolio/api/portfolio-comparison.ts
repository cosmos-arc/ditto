import type { components, operations } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";
import { RuntimeValidationError, recordValue, stringValue } from "@/api/validation";
import type { HistoryComparison, ModelHistory } from "./account-models";

export type PortfolioComparisonIdentity = operations["portfolio_get_comparison"]["parameters"]["query"];
export type PortfolioScenarioRequest = components["schemas"]["PortfolioScenarioBody"];
export type PortfolioComparison = components["schemas"]["PortfolioComparisonResponse"];
export type PortfolioScenarioPreview = components["schemas"]["PortfolioScenarioPreviewResponse"];
export type ModelHistoryIdentity = operations["portfolio_get_model_history"]["parameters"]["query"];
export type HistoryComparisonIdentity = operations["portfolio_get_history_comparison"]["parameters"]["query"];
export type { HistoryComparison, ModelHistory } from "./account-models";

import { assertPortfolioScenarioPreview, parseHistoryComparison, parseModelHistory } from "./runtime-validation";

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
	const comparison = await apiClient.get("/api/v1/portfolio/comparison", {
		params: { query: identity },
	});
	assertComparisonIdentity(identity, comparison);
	return comparison;
}

export async function fetchModelHistory(identity: ModelHistoryIdentity): Promise<ModelHistory> {
	const payload = await apiClient.get("/api/v1/portfolio/model-history", {
		params: { query: identity },
	});
	return parseModelHistory(payload, identity.strategy_id, identity);
}

export async function fetchHistoryComparison(identity: HistoryComparisonIdentity): Promise<HistoryComparison> {
	const payload = await apiClient.get("/api/v1/portfolio/history-comparison", {
		params: { query: identity },
	});
	return parseHistoryComparison(payload, identity);
}

export interface StrategyOption {
	readonly strategy_id: string;
	readonly name: string;
}

/**
 * Strategy picker options via the shared typed transport (no peer-feature
 * import). The endpoint returns a bare array; the first 100 strategies cover
 * the local-first catalog and the cap matches the backend `le` bound.
 */
export async function fetchStrategyOptions(): Promise<readonly StrategyOption[]> {
	const payload = await apiClient.get("/api/v1/strategies", {
		params: { query: { limit: 100 } },
	});
	if (!Array.isArray(payload)) {
		throw new RuntimeValidationError("strategyOptions", "payload", "expected an array");
	}
	return payload.map((entry, index) => {
		const boundary = `strategyOptions.${index}`;
		const entryRecord = recordValue(entry, boundary);
		return {
			strategy_id: stringValue(entryRecord, "strategy_id", boundary),
			name: stringValue(entryRecord, "name", boundary),
		};
	});
}

export async function previewPortfolioScenario(request: PortfolioScenarioRequest): Promise<PortfolioScenarioPreview> {
	const preview = await apiClient.post("/api/v1/portfolio/scenario-previews", { body: request });
	assertPortfolioScenarioPreview(preview);
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
