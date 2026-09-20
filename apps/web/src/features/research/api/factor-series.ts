import type { components, operations } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

type FactorSeriesOperation = operations["design_research_factor_evaluation_series"];
type FactorSeriesQuery = FactorSeriesOperation["parameters"]["query"];
export type FactorEvaluationSeriesResponse = components["schemas"]["FactorEvaluationSeriesResponse"];

export type FactorSeriesRequest = {
	readonly version?: number | undefined;
	readonly startDate?: string | undefined;
	readonly endDate?: string | undefined;
	readonly holdingPeriod?: number | undefined;
	readonly nQuantiles?: number | undefined;
	readonly rollingIrWindow?: number | undefined;
	readonly assetClass?: "stock" | "etf" | undefined;
	readonly adj?: "none" | "qfq" | "hfq" | undefined;
};

/** 查询时计算的因子评估逐日序列（IC/滚动 IR/分位净值/多空净值/月度 IC）。 */
export function fetchFactorEvaluationSeries(
	factorId: string,
	request: FactorSeriesRequest = {},
): Promise<FactorEvaluationSeriesResponse> {
	const query: FactorSeriesQuery = {};
	if (request.version !== undefined) query.version = request.version;
	if (request.startDate !== undefined) query.start_date = request.startDate;
	if (request.endDate !== undefined) query.end_date = request.endDate;
	if (request.holdingPeriod !== undefined) query.holding_period = request.holdingPeriod;
	if (request.nQuantiles !== undefined) query.n_quantiles = request.nQuantiles;
	if (request.rollingIrWindow !== undefined) query.rolling_ir_window = request.rollingIrWindow;
	if (request.assetClass !== undefined) query.asset_class = request.assetClass;
	if (request.adj !== undefined) query.adj = request.adj;
	return apiClient.get("/api/v1/research/factors/{factor_id}/evaluation-series", {
		params: { path: { factor_id: factorId }, query },
	});
}
