import { useMemo } from "react";
import { ApiError } from "@/api/errors";
import { ChartCockpit } from "@/components/chart";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { useBacktestBenchmark, useBacktestNav } from "../hooks";
import {
	alignedBenchmarkPoints,
	benchmarkGapCount,
	drawdownBands,
	drawdownPoints,
	excessPoints,
	formatNav,
	formatSignedPercent,
	normalizedNavPoints,
} from "../lib/nav-chart-mapping";

interface BacktestOverviewProps {
	readonly jobId: string;
}

export function BacktestOverview({ jobId }: BacktestOverviewProps) {
	const navQuery = useBacktestNav(jobId);
	const benchmarkQuery = useBacktestBenchmark(jobId);

	const navBars = useMemo(() => normalizedNavPoints(navQuery.data ?? []), [navQuery.data]);
	const benchmarkAvailable =
		!benchmarkQuery.isLoading && benchmarkQuery.data !== undefined && benchmarkQuery.data.dates.length > 0;
	const benchmarkBars = useMemo(
		() => (benchmarkAvailable ? alignedBenchmarkPoints(navBars, benchmarkQuery.data!) : []),
		[benchmarkAvailable, benchmarkQuery.data, navBars],
	);
	const hasBenchmark = benchmarkBars.length > 0;
	const excessBars = useMemo(
		() => (hasBenchmark ? excessPoints(navBars, benchmarkBars) : []),
		[hasBenchmark, navBars, benchmarkBars],
	);
	const drawdownBars = useMemo(() => drawdownPoints(navBars), [navBars]);
	const bands = useMemo(() => drawdownBands(navBars), [navBars]);
	const benchmarkGaps = useMemo(() => benchmarkGapCount(benchmarkBars), [benchmarkBars]);
	const drawdownDeepest = useMemo(() => {
		let deepest = 0;
		for (const bar of drawdownBars) {
			if (bar.close !== null && bar.close < deepest) deepest = bar.close;
		}
		return deepest;
	}, [drawdownBars]);

	if (navQuery.isLoading) {
		return <LoadingSkeleton variant="table" rows={6} />;
	}
	if (navQuery.error) {
		const message =
			navQuery.error instanceof ApiError
				? `${navQuery.error.status} ${navQuery.error.errorCode ?? "BACKTEST_NAV_ERROR"}: ${navQuery.error.message}`
				: navQuery.error.message;
		return (
			<div className="rounded-(--radius-md) border border-(--color-led-danger) bg-(--color-surface-1) p-4 text-xs">
				<p role="alert" className="text-(--color-led-danger)">
					{message}
				</p>
				<Button size="sm" variant="outline" className="mt-3" onClick={() => void navQuery.refetch()}>
					重试净值序列
				</Button>
			</div>
		);
	}

	const nav = navQuery.data ?? [];
	const lastNav = nav.at(-1)?.nav;
	const benchmark = benchmarkQuery.data;
	const lastBenchmarkNav = hasBenchmark ? benchmarkBars.at(-1)?.close ?? null : null;
	const lastBenchmarkRaw = benchmark?.navs.at(-1);
	const benchmarkError = benchmarkQuery.error;
	const benchmarkErrorText = benchmarkError
		? benchmarkError instanceof ApiError
			? `${benchmarkError.status} ${benchmarkError.errorCode ?? "BACKTEST_BENCHMARK_ERROR"}: ${benchmarkError.message}`
			: benchmarkError.message
		: null;
	// 基准缺失语义二分：404 = 未配置/未发布；200 空序列 = 已配置但本地行情无覆盖。
	const benchmarkUnconfigured = benchmarkError instanceof ApiError && benchmarkError.status === 404;

	return (
		<div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_20rem]">
			<section
				data-info-level="l2"
				data-info-unit="nav-curve"
				className="min-w-0 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
			>
				<div className="flex items-baseline justify-between gap-3">
					<div>
						<h3 className="text-sm font-semibold text-(--color-foreground)">净值 vs 基准</h3>
						<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">
							策略净值与基准归一到首点 1.0 叠加；回撤区间以主图底色 + 水下曲线呈现，读数与 KPI 同口径。
						</p>
					</div>
					<span className="font-data text-xs text-(--color-foreground-tertiary)">{nav.length} NAV POINTS</span>
				</div>
				{nav.length > 0 ? (
					<div className="mt-4" data-state={benchmarkGaps > 0 ? "benchmark-partial" : undefined}>
						{benchmarkGaps > 0 && (
							<p data-testid={`benchmark-gaps-${jobId}`} className="mb-2 text-xs text-(--color-foreground-muted)">
								基准缺口 {benchmarkGaps} 处（缺失区间断口渲染，不插值）
							</p>
						)}
						<ChartCockpit
							chartId={`backtest-nav-${jobId}`}
							rangeId={`backtest-${jobId}`}
							ariaLabel="策略净值与基准叠加，附超额收益与回撤水下曲线"
							height={360}
							series={[
								{
									id: "nav",
									label: "策略净值",
									bars: navBars,
									color: "var(--chart-run-1)",
									lineWidth: 2,
									format: formatNav,
								},
								...(hasBenchmark
									? [
											{
												id: "benchmark",
												label: "基准",
												bars: benchmarkBars,
												color: "var(--chart-series-neutral)",
												lineWidth: 1 as const,
												format: formatNav,
											},
										]
									: []),
							]}
							bands={bands}
							subPanes={[
								...(hasBenchmark
									? [
											{
												id: "excess",
												label: "超额收益（策略−基准）",
												series: [
													{
														id: "excess",
														label: "超额",
														points: excessBars,
														color: "var(--chart-run-2)",
														format: formatSignedPercent,
													},
												],
											},
										]
									: []),
								{
									id: "drawdown",
									label: "回撤（水下）",
									series: [
										{
											id: "drawdown",
											label: "回撤",
											points: drawdownBars,
											color: "var(--chart-series-down)",
											kind: "histogram" as const,
											format: formatSignedPercent,
										},
									],
									height: 104,
								},
							]}
							identity={{
								dataSourceName: "运行产物（nav.parquet + 基准行情归一）",
								knowledgeCutoff: null,
								publicationCutoff: null,
							}}
							exportName={`backtest-nav-${jobId}`}
						/>
					</div>
				) : (
					<p className="mt-8 text-xs text-(--color-foreground-tertiary)">运行尚未产出净值点。</p>
				)}
				{!benchmarkQuery.isLoading && !benchmarkErrorText && !benchmarkAvailable && nav.length > 0 && (
					<p data-state="benchmark-unavailable" className="mt-3 text-xs text-(--color-foreground-muted)">
						基准已配置，但本地行情无覆盖（基准数据不可得）
					</p>
				)}
				{benchmarkQuery.isLoading && (
					<p className="mt-3 text-xs text-(--color-foreground-tertiary)">正在加载基准…</p>
				)}
				{benchmarkUnconfigured && nav.length > 0 && (
					<p data-state="benchmark-unavailable" className="mt-3 text-xs text-(--color-foreground-muted)">
						本运行未配置基准（benchmark 未发布）
					</p>
				)}
				{benchmarkErrorText && !benchmarkUnconfigured && (
					<div data-state="benchmark-unavailable" className="mt-3 border-t border-(--color-border-subtle) pt-3">
						<p role="alert" className="text-xs text-(--color-led-danger)">
							{benchmarkErrorText}
						</p>
						<Button
							size="sm"
							variant="outline"
							className="mt-2"
							onClick={() => void benchmarkQuery.refetch()}
						>
							重试基准序列
						</Button>
					</div>
				)}
			</section>
			<aside
				data-info-level="l2"
				data-info-unit="nav-summary"
				className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
			>
				<h3 className="text-sm font-semibold text-(--color-foreground)">Series evidence</h3>
				<dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-3 text-xs">
					<dt className="text-(--color-foreground-tertiary)">策略末值</dt>
					<dd className="font-data text-(--color-foreground)">{lastNav?.toFixed(4) ?? "未发布"}</dd>
					<dt className="text-(--color-foreground-tertiary)">基准末值（归一）</dt>
					<dd className="font-data text-(--color-foreground)">
						{lastBenchmarkNav !== null ? lastBenchmarkNav.toFixed(4) : "未发布"}
					</dd>
					<dt className="text-(--color-foreground-tertiary)">基准收益</dt>
					<dd className="font-data text-(--color-foreground)">
						{benchmark?.benchmarkReturn === null || benchmark?.benchmarkReturn === undefined
							? "未发布"
							: `${benchmark.benchmarkReturn.toFixed(2)}%`}
					</dd>
					<dt className="text-(--color-foreground-tertiary)">基准点数</dt>
					<dd className="font-data text-(--color-foreground)">{benchmark?.navs.length ?? "未发布"}</dd>
					<dt className="text-(--color-foreground-tertiary)">最深回撤（水下曲线）</dt>
					<dd className="font-data text-(--color-foreground)">{formatSignedPercent(drawdownDeepest)}</dd>
					<dt className="text-(--color-foreground-tertiary)">回撤区间</dt>
					<dd className="font-data text-(--color-foreground)">{bands.length} 处</dd>
				</dl>
				<p className="mt-4 text-xs leading-5 text-(--color-foreground-muted)">
					净值证据至 {nav.at(-1)?.tradeDate ?? "—"}；策略与基准均归一到首点 1.0，末档原始基准值{" "}
					{lastBenchmarkRaw !== undefined ? lastBenchmarkRaw.toFixed(4) : "未发布"}。
				</p>
			</aside>
		</div>
	);
}
