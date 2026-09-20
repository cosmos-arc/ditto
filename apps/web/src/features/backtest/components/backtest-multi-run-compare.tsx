import { useQueries } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiError } from "@/api/errors";
import { ChartCockpit, ChartLegend } from "@/components/chart";
import { Button } from "@/components/ui/button";
import { fetchBacktestNav, fetchBacktestReport } from "../api/backtests";
import { backtestKeys } from "../hooks";
import { metricsRows, multiRunSeries, runColor } from "../lib/multi-run-mapping";
import type { BacktestNavPoint, BacktestReport, BacktestRun } from "../types";

/**
 * 多 run 净值叠加对比（≥2 个真实 run；#215 ②）。
 *
 * - 各 run 净值按 nav₀ 归一叠加（8 色 run 色板），图例 chip 控制显隐；
 *   色板索引绑定勾选序，隐藏不重排（CR：legend/曲线同色恒等）；
 * - 关键指标差异表按 run 原值呈现（年化/回撤为引擎百分数口径），
 *   未发布 report 的 run 标「未发布」，不虚构指标；
 * - 404 = 未落盘/未发布（业务态，诚实空位）；超时/5xx 等获取失败显式报错并可重试，
 *   不冒充缺席证据（CR）；PNG 导出 footer 内嵌有序 run 身份。
 */

type RunResources = {
	readonly run: BacktestRun;
	readonly nav: readonly BacktestNavPoint[];
	readonly navLoading: boolean;
	readonly report: BacktestReport | undefined;
	/** report 查询仍在进行——差异表标「读取中…」而非「未发布」。 */
	readonly reportPending: boolean;
	/** report 查询非 404 失败——差异表标「读取失败」。 */
	readonly reportFailed: boolean;
	/** 404 之外的获取失败（超时/5xx）——需显式暴露而非折叠为空数据。 */
	readonly fetchError: { readonly kind: "nav" | "report"; readonly cause: Error } | null;
};

function toFetchError(kind: "nav" | "report", error: unknown) {
	// 404 是业务态（未落盘/未发布），不属获取失败
	if (error instanceof ApiError && error.status === 404) return null;
	return { kind, cause: error instanceof Error ? error : new Error(String(error)) };
}

/** 选中集（≤8）逐 run 取 nav/report：useQueries 承接动态长度，hook 顺序稳定。 */
function useRunResources(runs: readonly BacktestRun[]) {
	const navs = useQueries({
		queries: runs.map((run) => ({
			queryKey: backtestKeys.nav(run.runId),
			queryFn: () => fetchBacktestNav(run.runId),
			// nav 404 与 report 同为真实业务态（run 未落盘 nav），不重试，
			// 404 落 data: undefined → 空 bars；其它错误走显式 fetchError。
			retry: false,
			throwOnError: false,
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
	const resources: RunResources[] = runs.map((run, index) => {
		// 两类错误都评估再择一：nav 404（业务态 → null）不能遮蔽同 run 的 report 5xx
		const navError = navs[index]?.isError ? toFetchError("nav", navs[index]?.error) : null;
		const reportError = reports[index]?.isError ? toFetchError("report", reports[index]?.error) : null;
		return {
			run,
			nav: navs[index]?.data ?? [],
			navLoading: navs[index]?.isLoading ?? false,
			report: reports[index]?.data,
			// report 查询状态传播到差异表：未定/失败期间不得标注「未发布」
			reportPending: reports[index]?.isLoading ?? false,
			reportFailed: reportError !== null,
			fetchError: navError ?? reportError,
		};
	});
	const refetchAll = () => {
		for (const result of [...navs, ...reports]) void result.refetch();
	};
	return { resources, refetchAll };
}

export function BacktestMultiRunCompare({ runs }: { readonly runs: readonly BacktestRun[] }) {
	const { resources, refetchAll } = useRunResources(runs);
	const [hiddenRuns, setHiddenRuns] = useState<ReadonlySet<string>>(new Set());
	// 色板绑定勾选序：先按全量选中集着色再过滤显隐，隐藏不重排剩余序列的颜色
	const series = useMemo(
		() =>
			multiRunSeries(resources.map((item) => ({ runId: item.run.runId, nav: item.nav }))).filter(
				(spec) => !hiddenRuns.has(spec.id),
			),
		[resources, hiddenRuns],
	);
	const reports = useMemo(
		() =>
			new Map(
				resources.map((item) => [
					item.run.runId,
					{ report: item.report, pending: item.reportPending, failed: item.reportFailed },
				]),
			),
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
	const fetchError = resources.find((item) => item.fetchError)?.fetchError ?? null;
	// PNG/CSV 导出 footer 内嵌 run 身份：跟随可见序列——隐藏 run 的数据不在导出物里，
	// 身份不得声称其参与（导出物无 DOM 图例可供读者发现差异）
	const visibleRunIds = useMemo(
		() => resources.filter((item) => !hiddenRuns.has(item.run.runId)).map((item) => item.run.runId),
		[resources, hiddenRuns],
	);
	const identity = useMemo(
		() => ({
			dataSourceName: `运行产物（各 run nav.parquet，nav₀ 归一）：${visibleRunIds.join(" · ")}`,
			snapshotId: null,
			knowledgeCutoff: null,
			publicationCutoff: null,
		}),
		[visibleRunIds],
	);

	return (
		<div className="flex min-w-0 flex-col gap-4" data-testid="backtest-multi-run-compare">
			<ChartLegend
				ariaLabel="净值叠加序列显隐"
				testId="multi-run-legend"
				items={resources.map((item, index) => ({
					id: item.run.runId,
					label: item.run.runId,
					color: runColor(index),
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
			{fetchError ? (
				<div
					role="alert"
					data-state="fetch-error"
					className="flex flex-col items-start gap-2 rounded-(--radius-md) border border-(--color-risk-critical-fg) bg-(--color-surface-1) p-4 text-xs"
				>
					<p className="font-medium text-(--color-foreground)">
						{fetchError.kind === "nav" ? "净值" : "report"}证据读取失败：{fetchError.cause.message}
					</p>
					<p className="text-(--color-foreground-secondary)">
						获取失败不会折算为「未发布」或空净值；404 才是未落盘/未发布的业务态。
					</p>
					<Button type="button" size="sm" variant="outline" onClick={refetchAll}>
						重试读取所选 run 证据
					</Button>
				</div>
			) : navLoading ? (
				<div
					className="flex h-64 items-center justify-center rounded-(--radius-md) border border-(--color-border-subtle) text-xs text-(--color-foreground-tertiary)"
					data-state="loading"
				>
					正在读取所选 run 的净值证据…
				</div>
			) : series.every((spec) => spec.bars.length === 0) ? (
				// 可见 run 均未落盘 nav（404 业务态）：结构化空态而非空白画布。
				// 结论基于未过滤的选中集区分两种情形——隐藏的 run 可能仍有数据。
				<div
					className="flex h-64 flex-col items-center justify-center gap-2 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-4 text-center text-xs text-(--color-foreground-secondary)"
					data-state="nav-empty"
				>
					<p>
						{resources.every((item) => item.nav.length === 0)
							? "所选 run 均未落盘净值证据（无 nav.parquet）。"
							: "当前可见 run 均未落盘净值证据；隐藏的 run 中仍有数据，点击图例恢复。"}
					</p>
					<p className="text-(--color-foreground-tertiary)">指标差异表仍按各 run report 状态呈现。</p>
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
				图内曲线按各 run 首日净值归一（跨初始资金可比）；表内为 run 原值，金额单位 CNY。未发布 report 的 run
				指标不可得，如实标注。
			</p>
		</div>
	);
}
