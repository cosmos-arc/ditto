import { useQueries } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ChartCockpit, ChartLegend } from "@/components/chart";
import { fetchBacktestNav, fetchBacktestReport } from "../api/backtests";
import { backtestKeys } from "../hooks";
import { metricsRows, multiRunSeries } from "../lib/multi-run-mapping";
import type { BacktestNavPoint, BacktestReport, BacktestRun } from "../types";

/**
 * 多 run 净值叠加对比（≥2 个真实 run；#215 ②）。
 *
 * - 各 run 净值按 nav₀ 归一叠加（8 色 run 色板），图例 chip 控制显隐；
 * - 关键指标差异表按 run 原值呈现（年化/回撤为引擎百分数口径），
 *   未发布 report 的 run 标「未发布」，不虚构指标；
 * - 每条序列来自该 run 已落盘 nav 证据，缺 nav 的 run 图上无曲线但保留图例位。
 */

type RunResources = {
	readonly run: BacktestRun;
	readonly nav: readonly BacktestNavPoint[];
	readonly navLoading: boolean;
	readonly report: BacktestReport | undefined;
};

/** 选中集（≤8）逐 run 取 nav/report：useQueries 承接动态长度，hook 顺序稳定。 */
function useRunResources(runs: readonly BacktestRun[]): RunResources[] {
	const navs = useQueries({
		queries: runs.map((run) => ({
			queryKey: backtestKeys.nav(run.runId),
			queryFn: () => fetchBacktestNav(run.runId),
		})),
	});
	const reports = useQueries({
		queries: runs.map((run) => ({
			queryKey: backtestKeys.report(run.runId),
			queryFn: () => fetchBacktestReport(run.runId),
			// report 404 是真实业务态（未发布），不按 error 处理而是 data: undefined。
			retry: false,
			throwOnError: false,
		})),
	});
	return runs.map((run, index) => ({
		run,
		nav: navs[index]?.data ?? [],
		navLoading: navs[index]?.isLoading ?? false,
		report: reports[index]?.data,
	}));
}

export function BacktestMultiRunCompare({ runs }: { readonly runs: readonly BacktestRun[] }) {
	const resources = useRunResources(runs);
	const [hiddenRuns, setHiddenRuns] = useState<ReadonlySet<string>>(new Set());
	const visible = useMemo(() => resources.filter((item) => !hiddenRuns.has(item.run.runId)), [resources, hiddenRuns]);
	const series = useMemo(
		() => multiRunSeries(visible.map((item) => ({ runId: item.run.runId, nav: item.nav }))),
		[visible],
	);
	const reports = useMemo(
		() =>
			new Map(resources.filter((item) => item.report).map((item) => [item.run.runId, item.report as BacktestReport])),
		[resources],
	);
	const rows = useMemo(
		() =>
			metricsRows(
				resources.map((item) => item.run),
				reports,
			),
		[resources, reports],
	);
	const navLoading = resources.some((item) => item.navLoading);
	const identity = useMemo(
		() => ({
			dataSourceName: "运行产物（各 run nav.parquet，按 nav₀ 归一）",
			snapshotId: null,
			knowledgeCutoff: null,
			publicationCutoff: null,
		}),
		[],
	);

	return (
		<div className="flex min-w-0 flex-col gap-4" data-testid="backtest-multi-run-compare">
			<ChartLegend
				ariaLabel="净值叠加序列显隐"
				testId="multi-run-legend"
				items={resources.map((item, index) => ({
					id: item.run.runId,
					label: item.run.runId,
					color: `var(--chart-run-${(index % 8) + 1})`,
					visible: !hiddenRuns.has(item.run.runId),
				}))}
				onToggle={(runId) =>
					setHiddenRuns((previous) => {
						const next = new Set(previous);
						if (next.has(runId)) {
							next.delete(runId);
						} else if (previous.size < resources.length - 1) {
							// 至少保留一条序列：全部隐藏后图表失去对比锚点。
							next.add(runId);
						} else {
							return previous;
						}
						return next;
					})
				}
			/>
			{navLoading ? (
				<div
					className="flex h-64 items-center justify-center rounded-(--radius-md) border border-(--color-border-subtle) text-xs text-(--color-foreground-tertiary)"
					data-state="loading"
				>
					正在读取所选 run 的净值证据…
				</div>
			) : (
				<ChartCockpit
					chartId="backtest-multi-run-nav"
					rangeId="backtest-multi-run-nav"
					ariaLabel="多 run 归一化净值叠加"
					height={320}
					series={series}
					identity={identity}
				/>
			)}
			<div className="min-w-0 overflow-x-auto">
				<table className="w-full min-w-3xl border-collapse text-xs" data-testid="multi-run-metrics">
					<thead>
						<tr className="border-b border-(--color-border-subtle) text-left uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
							<th className="px-2 py-2 font-medium">Run</th>
							<th className="px-2 py-2 font-medium">Period</th>
							<th className="px-2 py-2 text-right font-medium">Initial cash</th>
							<th className="px-2 py-2 text-right font-medium">Final NAV</th>
							<th className="px-2 py-2 text-right font-medium">年化收益</th>
							<th className="px-2 py-2 text-right font-medium">最大回撤</th>
							<th className="px-2 py-2 text-right font-medium">Sharpe</th>
						</tr>
					</thead>
					<tbody>
						{rows.map((row) => (
							<tr
								key={row.runId}
								className="border-b border-(--color-border-subtle) last:border-b-0"
								data-run-id={row.runId}
								data-report-published={row.reportPublished}
							>
								<td className="max-w-56 truncate px-2 py-2 font-data text-(--color-foreground)">{row.runId}</td>
								<td className="px-2 py-2 font-data text-(--color-foreground-secondary)">{row.period}</td>
								<td className="px-2 py-2 text-right font-data tabular-nums text-(--color-foreground-secondary)">
									{row.initialCash}
								</td>
								<td className="px-2 py-2 text-right font-data tabular-nums text-(--color-foreground-secondary)">
									{row.finalNav}
								</td>
								<td className="px-2 py-2 text-right font-data tabular-nums text-(--color-foreground)">
									{row.annualizedReturn}
								</td>
								<td className="px-2 py-2 text-right font-data tabular-nums text-(--color-foreground-secondary)">
									{row.maxDrawdown}
								</td>
								<td className="px-2 py-2 text-right font-data tabular-nums text-(--color-foreground-secondary)">
									{row.sharpe}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
			<p className="text-[11px] text-(--color-foreground-tertiary)">
				图内曲线按各 run 首日净值归一（跨初始资金可比）；表内为 run 原值。未发布 report 的 run 指标不可得，如实标注。
			</p>
		</div>
	);
}
