import { ApiError } from "@/api";
import { AreaChart } from "@/components/chart/area-chart";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { useBacktestBenchmark, useBacktestNav } from "../hooks";

interface BacktestOverviewProps {
	readonly jobId: string;
}

export function BacktestOverview({ jobId }: BacktestOverviewProps) {
	const navQuery = useBacktestNav(jobId);
	const benchmarkQuery = useBacktestBenchmark(jobId);

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
	const benchmark = benchmarkQuery.data;
	const lastNav = nav.at(-1)?.nav;
	const lastBenchmark = benchmark?.navs.at(-1);
	const benchmarkError = benchmarkQuery.error;
	const benchmarkErrorText = benchmarkError
		? benchmarkError instanceof ApiError
			? `${benchmarkError.status} ${benchmarkError.errorCode ?? "BACKTEST_BENCHMARK_ERROR"}: ${benchmarkError.message}`
			: benchmarkError.message
		: null;

	return (
		<div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_20rem]">
			<section
				data-info-level="l2"
				data-info-unit="nav-curve"
				className="min-w-0 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
			>
				<div className="flex items-baseline justify-between gap-3">
					<div>
						<h3 className="text-sm font-semibold text-(--color-foreground)">净值与基准</h3>
						<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">策略净值使用运行产出的逐日 NAV。</p>
					</div>
					<span className="font-data text-xs text-(--color-foreground-tertiary)">{nav.length} NAV POINTS</span>
				</div>
				{nav.length > 0 ? (
					<AreaChart
						data={nav.map((point) => ({ time: point.tradeDate, value: point.nav }))}
						height={280}
						showAxes
						className="mt-4"
					/>
				) : (
					<p className="mt-8 text-xs text-(--color-foreground-tertiary)">运行尚未产出净值点。</p>
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
					<dt className="text-(--color-foreground-tertiary)">基准末值</dt>
					<dd className="font-data text-(--color-foreground)">{lastBenchmark?.toFixed(4) ?? "未发布"}</dd>
					<dt className="text-(--color-foreground-tertiary)">基准收益</dt>
					<dd className="font-data text-(--color-foreground)">
						{benchmark?.benchmarkReturn === null || benchmark?.benchmarkReturn === undefined
							? "未发布"
							: `${benchmark.benchmarkReturn.toFixed(2)}%`}
					</dd>
					<dt className="text-(--color-foreground-tertiary)">基准点数</dt>
					<dd className="font-data text-(--color-foreground)">{benchmark?.navs.length ?? "未发布"}</dd>
				</dl>
				{benchmarkQuery.isLoading && <p className="mt-4 text-xs text-(--color-foreground-tertiary)">正在加载基准…</p>}
				{benchmarkErrorText && (
					<div className="mt-4 border-t border-(--color-border-subtle) pt-3">
						<p role="alert" className="text-xs text-(--color-led-danger)">
							{benchmarkErrorText}
						</p>
						<Button size="sm" variant="outline" className="mt-2" onClick={() => void benchmarkQuery.refetch()}>
							重试基准序列
						</Button>
					</div>
				)}
			</aside>
		</div>
	);
}
