import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { Panel } from "@/features/shell/components/panel";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useDecisionBanner } from "../hooks";

function signedMoney(value: number | null): string {
	if (value == null) return "不可用";
	return `${value >= 0 ? "+" : ""}¥${value.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`;
}

function signedPercent(value: number | null): string {
	if (value == null) return "不可用";
	return `${value >= 0 ? "+" : ""}${value.toFixed(3)}%`;
}

function metric(value: number | null, suffix = ""): string {
	return value == null ? "不可用" : `${value}${suffix}`;
}

export function BannerSection() {
	const { data, isLoading, refetch } = useDecisionBanner();

	if (isLoading) {
		return <LoadingSkeleton variant="panel" />;
	}

	return (
		<div data-info-level="l1" data-info-unit="decision-banner" className="h-24 flex-none">
			<DittoErrorBoundary
				fallbackProps={{
					title: "决策横幅加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<Panel className="h-full flex-none">
						<section
							data-slot="decision-banner"
							data-testid="decision-banner"
							className="grid h-full grid-cols-[minmax(280px,4fr)_minmax(360px,5fr)_minmax(174px,2fr)] gap-3 overflow-hidden"
						>
							<div className="min-w-0 pt-1">
								<span className="text-xs text-(--color-foreground-tertiary)">今日主决策</span>
								<p className="mt-1 line-clamp-2 text-base font-semibold leading-snug text-(--color-foreground)">
									{data.suggestion}
								</p>
								<p className="mt-1 truncate text-xs text-(--color-foreground-tertiary)">
									{data.regimeType} · 权益{" "}
									{data.totalEquity == null ? "不可用" : `¥${data.totalEquity.toLocaleString("zh-CN")}`}
								</p>
							</div>

							<div className="min-w-0 border-l border-(--color-border-subtle)">
								<div className="grid grid-cols-3 gap-1.5">
									{[
										{ label: "杠杆率", value: metric(data.leverage, "x") },
										{ label: "回撤", value: metric(data.maxDrawdown, "%") },
										{ label: "风险利用率", value: metric(data.riskUtilization, "%") },
									].map((impact) => (
										<div
											key={impact.label}
											className="h-[68px] min-w-0 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-elevated)/60 px-2 py-1.5"
										>
											<p className="truncate text-xs text-(--color-foreground-tertiary)">{impact.label}</p>
											<p className="mt-0.5 truncate font-data text-xs font-semibold text-(--color-foreground)">
												{impact.value}
											</p>
										</div>
									))}
								</div>
								<p className="mt-1.5 truncate text-xs text-(--color-foreground-tertiary)">
									今日盈亏 {signedMoney(data.dailyPnl)} · {signedPercent(data.dailyPnlPercent)}
								</p>
							</div>

							<div className="min-w-0 border-l border-(--color-border-subtle) pt-1 pl-4">
								<span className="text-xs text-(--color-foreground-tertiary)">下一步</span>
								<div className="mt-1.5 flex gap-1.5">
									<Button asChild variant="outline" size="xs" className="border-(--color-accent) text-(--color-accent)">
										<a href="/portfolio/review">复核信号</a>
									</Button>
									<Button asChild variant="ghost" size="xs">
										<a href="/risk">查看风控</a>
									</Button>
								</div>
							</div>
						</section>
					</Panel>
				)}
			</DittoErrorBoundary>
		</div>
	);
}
