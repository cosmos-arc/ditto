import { apiClient, withQueryParams } from "@/lib/api-client";
import type { GetComparisonAttributionResponse } from "@/types";
import type { components } from "@/types/generated/api";
import { DEFAULT_STRATEGY_ID } from "./query-keys";

type ComparisonMetricsResponse = components["schemas"]["ComparisonMetricsResponse"];

export interface FetchComparisonParams {
	readonly strategyId?: string;
	readonly runId: string;
}

function formatBps(value: number | null | undefined): string {
	return value == null ? "—" : `${value.toFixed(1)} bps`;
}

function formatPercent(value: number | null | undefined): string {
	return value == null ? "—" : `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value: number | null | undefined): string {
	return value == null ? "—" : value.toFixed(2);
}

function mapComparisonMetrics(metrics: ComparisonMetricsResponse): GetComparisonAttributionResponse {
	const sharpeDiff = metrics.actual_sharpe - metrics.backtest_sharpe;

	return {
		rows: [
			{
				label: "收益差异",
				value: formatBps(metrics.return_diff_bps),
				detail: `actual ${formatPercent(metrics.actual_return)} vs backtest ${formatPercent(metrics.backtest_return)}`,
			},
			{
				label: "成本拖累",
				value: formatBps(metrics.cost_drag_bps),
				detail: `actual cost ${formatNumber(metrics.actual_total_cost)} vs backtest cost ${formatNumber(metrics.backtest_total_cost)}`,
			},
			{
				label: "跟踪误差",
				value: formatBps(metrics.avg_daily_tracking_error_bps),
				detail: `NAV corr ${metrics.nav_correlation.toFixed(4)}, max diff ${formatBps(metrics.max_nav_diff_bps)}`,
			},
			{
				label: "Sharpe 差异",
				value: sharpeDiff.toFixed(2),
				detail: `actual ${metrics.actual_sharpe.toFixed(2)} vs backtest ${metrics.backtest_sharpe.toFixed(2)}`,
			},
		],
	};
}

export async function fetchComparisonAttribution({
	strategyId = DEFAULT_STRATEGY_ID,
	runId,
}: FetchComparisonParams): Promise<GetComparisonAttributionResponse> {
	const metrics = await apiClient.get<ComparisonMetricsResponse>(
		withQueryParams("/v1/manual/comparison", {
			strategy_id: strategyId,
			run_id: runId,
		}),
	);

	return mapComparisonMetrics(metrics);
}
