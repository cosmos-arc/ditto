import { ApiError } from "@/api";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { useBacktestReport } from "../hooks";

interface BacktestReturnsViewProps {
	readonly jobId: string;
}

export function BacktestReturnsView({ jobId }: BacktestReturnsViewProps) {
	const query = useBacktestReport(jobId);

	if (query.isLoading) {
		return <LoadingSkeleton variant="table" rows={6} />;
	}
	if (query.error || !query.data) {
		const message = query.error
			? query.error instanceof ApiError
				? `${query.error.status} ${query.error.errorCode ?? "BACKTEST_REPORT_ERROR"}: ${query.error.message}`
				: query.error.message
			: "报告尚未发布";
		return (
			<div className="rounded-(--radius-md) border border-(--color-led-danger) bg-(--color-surface-1) p-4 text-xs">
				<p role="alert" className="text-(--color-led-danger)">
					{message}
				</p>
				<Button size="sm" variant="outline" className="mt-3" onClick={() => void query.refetch()}>
					重试收益报告
				</Button>
			</div>
		);
	}

	const report = query.data;
	const alpha = report.alphaStats;
	const trades = report.tradeStats;
	const money = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
	const metric = (value: number | null | undefined, suffix = "") =>
		value === null || value === undefined ? "未评估" : `${value.toFixed(2)}${suffix}`;

	return (
		<div className="grid min-w-0 gap-3 xl:grid-cols-[20rem_minmax(0,1fr)]">
			<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-4">
				<h3 className="text-sm font-semibold text-(--color-foreground)">Performance report</h3>
				<p className="mt-1 text-xs text-(--color-foreground-tertiary)">报告元数据绑定当前 run，不推导月收益。</p>
				<dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-3 text-xs">
					<dt className="text-(--color-foreground-tertiary)">期间</dt>
					<dd className="font-data">
						{report.periodStart || "未发布"} → {report.periodEnd || "未发布"}
					</dd>
					<dt className="text-(--color-foreground-tertiary)">初始资金</dt>
					<dd className="font-data">¥ {money.format(report.initialCash)}</dd>
					<dt className="text-(--color-foreground-tertiary)">最终净值</dt>
					<dd className="font-data">{report.finalNav.toFixed(4)}</dd>
					<dt className="text-(--color-foreground-tertiary)">调仓频率</dt>
					<dd className="font-data">{report.rebalanceFreq || "未发布"}</dd>
				</dl>
			</section>
			<div className="grid gap-3 lg:grid-cols-2">
				<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-4">
					<h3 className="text-xs font-semibold uppercase tracking-[0.06em] text-(--color-foreground-tertiary)">
						Alpha statistics
					</h3>
					<dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2.5 text-xs">
						<dt>年化波动</dt>
						<dd className="font-data">{metric(alpha && alpha.annualizedVolatility * 100, "%")}</dd>
						<dt>Calmar</dt>
						<dd className="font-data">{metric(alpha?.calmarRatio)}</dd>
						<dt>Information ratio</dt>
						<dd className="font-data">{metric(alpha?.informationRatio)}</dd>
						<dt>Beta</dt>
						<dd className="font-data">{metric(alpha?.beta)}</dd>
						<dt>年化 Alpha</dt>
						<dd className="font-data">
							{metric(
								alpha?.alphaAnnualized === null || alpha?.alphaAnnualized === undefined
									? null
									: alpha.alphaAnnualized * 100,
								"%",
							)}
						</dd>
						<dt>费用拖累</dt>
						<dd className="font-data">{metric(alpha && alpha.costDrag * 100, "%")}</dd>
					</dl>
				</section>
				<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-4">
					<h3 className="text-xs font-semibold uppercase tracking-[0.06em] text-(--color-foreground-tertiary)">
						Trade statistics
					</h3>
					<dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2.5 text-xs">
						<dt>总成交</dt>
						<dd className="font-data">{trades?.totalTrades ?? "未评估"}</dd>
						<dt>盈利 / 亏损</dt>
						<dd className="font-data">{trades ? `${trades.winTrades} / ${trades.lossTrades}` : "未评估"}</dd>
						<dt>Profit factor</dt>
						<dd className="font-data">{metric(trades?.profitFactor)}</dd>
						<dt>平均盈亏比</dt>
						<dd className="font-data">{metric(trades?.avgWinLossRatio)}</dd>
						<dt>平均持有日</dt>
						<dd className="font-data">{metric(trades?.avgHoldingDays)}</dd>
						<dt>最佳 / 最差</dt>
						<dd className="font-data">
							{trades ? `${money.format(trades.bestTrade)} / ${money.format(trades.worstTrade)}` : "未评估"}
						</dd>
					</dl>
				</section>
			</div>
		</div>
	);
}
