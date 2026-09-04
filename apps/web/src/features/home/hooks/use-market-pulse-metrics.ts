import { useQuery } from "@tanstack/react-query";
import { fetchCurrentMarketContext, type MarketContext } from "@/features/markets/api/market-evidence";
import { apiClient } from "@/lib/api-client";
import type { GetMarketPulseMetricsResponse } from "@/types";
import { shouldUseHomePrototypeMocks } from "../api/runtime";

const REGIME_LABELS: Record<NonNullable<MarketContext["regime_label"]>, string> = {
	risk_on: "风险偏好",
	balanced: "均衡",
	risk_off: "风险规避",
};

const STATUS_LABELS: Record<MarketContext["status"], string> = {
	ready: "可用",
	degraded: "降级",
	blocked: "阻断",
};

const METRIC_LABELS: Record<string, string> = {
	advance_decline_breadth: "市场宽度",
	benchmark_return_20d: "沪深300 20日",
	benchmark_volatility_20d: "实现波动率",
	commodity_return_1d: "商品市场 1日",
	fx_return_1d: "汇率市场 1日",
	global_return_1d: "全球市场 1日",
	macro_surprise_score: "宏观意外",
	macro_trend_score: "宏观趋势",
	small_large_cap_return_spread_20d: "小盘 / 大盘 20日",
};

const TREND_LABELS: Record<MarketContext["metrics"][number]["trend"], string> = {
	rising: "上行",
	falling: "下行",
	flat: "平稳",
	mixed: "分化",
	unknown: "趋势未知",
};

function signed(value: number, digits: number): string {
	return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function metricValue(metric: MarketContext["metrics"][number]): string {
	if (metric.unit === "ratio") {
		const value = metric.value * 100;
		return metric.name === "advance_decline_breadth" ? `${value.toFixed(1)}%` : `${signed(value, 2)}%`;
	}
	if (metric.unit === "score") return signed(metric.value, 2);
	return `${metric.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })} ${metric.unit}`.trim();
}

function riskItems(context: MarketContext): readonly string[] {
	return [
		...context.impacts
			.filter((impact) => impact.direction === "pressuring")
			.map((impact) => `${impact.target_domain} · ${impact.target}：${impact.rationale_driver}`),
		...context.data_conflicts.map((item) => `数据冲突：${item}`),
		...context.missing_inputs.map((item) => `缺失输入：${item}`),
		...context.uncertainties.map((item) => `不确定性：${item}`),
	];
}

export function marketContextToPulse(context: MarketContext): GetMarketPulseMetricsResponse {
	const regimeLabel = context.regime_label === null ? "等待证据" : REGIME_LABELS[context.regime_label];
	const score = context.regime_score === null ? "得分不可用" : `得分 ${signed(context.regime_score, 2)}`;
	return {
		brief: {
			asOf: context.as_of,
			drivers: context.drivers,
			evidenceRefs: context.evidence_refs,
			featureSetId: context.feature_set_id,
			knowledgeCutoff: context.knowledge_cutoff,
			publicationCutoff: context.publication_cutoff,
			regimeLabel,
			regimeScore: context.regime_score,
			riskItems: riskItems(context),
			sourceSnapshotIds: context.source_snapshot_ids,
			sourceSnapshotSetId: context.source_snapshot_set_id,
			status: context.status,
			statusLabel: STATUS_LABELS[context.status],
		},
		metrics: [
			{
				change: `${STATUS_LABELS[context.status]} · ${score}`,
				label: "市场环境",
				value: regimeLabel,
			},
			...context.metrics.map((metric) => ({
				change: TREND_LABELS[metric.trend],
				label: METRIC_LABELS[metric.name] ?? metric.name,
				value: metricValue(metric),
			})),
		],
	};
}

export function useMarketPulseMetrics() {
	const useMocks = shouldUseHomePrototypeMocks();
	const liveQuery = useQuery({
		queryKey: ["market-evidence", "context", "current"],
		queryFn: () => fetchCurrentMarketContext(),
		select: marketContextToPulse,
		staleTime: 60_000,
		enabled: !useMocks,
	});
	const mockQuery = useQuery({
		queryKey: ["market", "pulse-metrics"],
		queryFn: () => apiClient.get<GetMarketPulseMetricsResponse>("/home/pulse-metrics"),
		enabled: useMocks,
	});
	return useMocks ? mockQuery : liveQuery;
}
