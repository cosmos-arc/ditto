import { useMemo } from "react";
import { ApiError } from "@/api/errors";
import { ChartCockpit } from "@/components/chart";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { useFactorEvaluationSeries } from "../hooks/use-factor-detail";
import { heatmapBucket, icSeries, monthlyIcRows, quantileSeries } from "../lib/factor-series-mapping";

const MONTH_LABELS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

/**
 * 因子研究图表工作台：IC/滚动 IR 双轴、Q1–QN 分位净值 + 多空 spread、月度 IC 热力图。
 * 序列由查询时计算（同一评估函数族），前向收益 look-ahead → 仅研究/测试环境。
 */
export function FactorSeriesCharts({
	factorId,
	startDate,
	endDate,
}: {
	readonly factorId: string;
	readonly startDate: string;
	readonly endDate: string;
}) {
	const query = useFactorEvaluationSeries(factorId, { assetClass: "etf", endDate, startDate });

	const icSpecs = useMemo(() => (query.data ? icSeries(query.data) : []), [query.data]);
	const quantileSpecs = useMemo(() => (query.data ? quantileSeries(query.data) : []), [query.data]);
	const heatmapRows = useMemo(() => (query.data ? monthlyIcRows(query.data) : []), [query.data]);

	if (query.isLoading) return <LoadingSkeleton variant="chart" />;
	if (query.error) {
		const message =
			query.error instanceof ApiError
				? `${query.error.status} ${query.error.errorCode ?? "FACTOR_SERIES_ERROR"}: ${query.error.message}`
				: query.error.message;
		return (
			<div
				data-state="series-unavailable"
				className="rounded-(--radius-md) border border-(--color-border-subtle) p-4 text-xs text-(--color-foreground-tertiary)"
			>
				<p role="alert" className="text-(--color-led-danger)">
					{message}
				</p>
				<p className="mt-1">评估序列为研究语义（前向收益 look-ahead），生产环境 fail closed。</p>
			</div>
		);
	}
	if (!query.data || query.data.n_dates === 0) {
		return (
			<p data-state="series-empty" className="p-4 text-xs text-(--color-foreground-tertiary)">
				该窗口没有可评估的因子数据（分位/IC 序列为空）。
			</p>
		);
	}

	return (
		<div data-info-level="l2" data-info-unit="factor-series-charts" className="flex flex-col gap-4">
			<div data-testid={`factor-ic-chart-${factorId}`}>
				<ChartCockpit
					chartId={`factor-ic-${factorId}`}
					rangeId={`factor-${factorId}`}
					ariaLabel="Rank IC 时序与滚动 IR 双轴图"
					height={200}
					series={icSpecs}
					identity={{
						dataSourceName: "查询时评估（derived artifact + 本地行情前向收益）",
						knowledgeCutoff: query.data.period_end,
					}}
					exportName={`factor-ic-${factorId}`}
				/>
			</div>
			<div data-testid={`factor-quantile-chart-${factorId}`}>
				<ChartCockpit
					chartId={`factor-quantile-${factorId}`}
					rangeId={`factor-${factorId}`}
					ariaLabel="Q1 至 Q5 分位分层净值与多空 spread"
					height={260}
					series={quantileSpecs}
					identity={{
						dataSourceName: "查询时评估（分位组合逐日收益累计）",
						knowledgeCutoff: query.data.period_end,
					}}
					exportName={`factor-quantile-${factorId}`}
				/>
			</div>
			<section className="overflow-x-auto rounded-(--radius-md) border border-(--color-border-subtle)">
				<table data-testid={`factor-monthly-ic-${factorId}`} className="w-full min-w-[40rem] border-collapse text-xs">
					<caption className="sr-only">月度 Rank IC 热力图（红正绿负，深浅表示幅度）</caption>
					<thead>
						<tr className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
							<th scope="col" className="px-2 py-1.5 text-left font-medium">
								年份
							</th>
							{MONTH_LABELS.map((label) => (
								<th key={label} scope="col" className="px-2 py-1.5 text-center font-medium">
									{label}
								</th>
							))}
						</tr>
					</thead>
					<tbody className="font-data tabular-nums">
						{heatmapRows.map((row) => (
							<tr key={row.year} className="border-t border-(--color-border-subtle)">
								<th scope="row" className="px-2 py-1.5 text-left font-medium text-(--color-foreground-secondary)">
									{row.year}
								</th>
								{row.cells.map((cell) => (
									<td
										key={cell.month}
										className="heat-cell px-2 py-1.5 text-center"
										data-heat={heatmapBucket(cell.meanIc)}
										title={
											cell.meanIc === null
												? "无数据"
												: `${row.year}-${cell.month} IC ${cell.meanIc.toFixed(3)}（${cell.days} 日）`
										}
									>
										{cell.meanIc === null ? "—" : cell.meanIc.toFixed(3)}
									</td>
								))}
							</tr>
						))}
					</tbody>
				</table>
			</section>
			<p className="text-xs text-(--color-foreground-muted)">
				窗口 {query.data.period_start} → {query.data.period_end} · {query.data.n_dates} 个评估日 · 持有期{" "}
				{query.data.holding_period} 日 · 分位 {query.data.n_quantiles} 组；读数与不可变诊断同源同函数族。
			</p>
		</div>
	);
}
