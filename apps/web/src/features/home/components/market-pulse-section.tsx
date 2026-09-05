import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import type { SparklineColor } from "@/components/data/sparkline";
import { Sparkline } from "@/components/data/sparkline";
import { ContextSection } from "@/components/domain/context-section";
import { ScrollReveal } from "@/components/ui/scroll-reveal";
import { type LoadMarketContext, useMarketPulseMetrics } from "../hooks";

const DRIVER_LABELS: Record<string, string> = {
	breadth: "市场宽度",
	volatility: "波动率",
};

const DIRECTION_LABELS = {
	supportive: "支撑",
	pressuring: "承压",
	neutral: "中性",
} as const;

/** Derive sparkline color from the change string. */
function changeToColor(change: string): SparklineColor {
	if (change.startsWith("+")) return "up";
	if (change.startsWith("-")) return "down";
	return "neutral";
}

/** Map change string + direction to a CSS text color class. */
function changeTextColor(change: string): string {
	if (change.startsWith("+")) return "text-(--color-market-up-fg)";
	if (change.startsWith("-")) return "text-(--color-market-down-fg)";
	return "text-(--color-foreground-tertiary)";
}

/**
 * MarketPulseSection -- sidebar "市场脉搏" section.
 * Matches prototype .pulse-metric items: label + value/change + optional sparkline.
 * Consumes MarketPulseMetric mock data (4 metrics with inline sparklines).
 */
export function MarketPulseSection({
	loadMarketContext,
}: {
	readonly loadMarketContext?: LoadMarketContext | undefined;
}) {
	const { data, error, isError, isLoading } = useMarketPulseMetrics(loadMarketContext);

	return (
		<ContextSection
			title="市场脉搏"
			defaultOpen
			data-info-level="l1"
			data-info-unit="market-pulse"
			className="[&_[data-slot=context-section-header]>span:first-child]:ml-2 [&_[data-slot=context-section-header]>span:first-child]:pl-2.5"
		>
			{isLoading && <LoadingSkeleton variant="table" rows={4} />}
			{isError && (
				<div role="alert" className="mx-2 rounded-(--radius-sm) border border-(--color-risk-high-border) p-2 text-xs">
					<p className="font-medium text-(--color-risk-high-fg)">MarketContext 不可用</p>
					<p className="mt-1 text-(--color-foreground-tertiary)">
						{error instanceof Error ? error.message : "无法解析认证数据证据"}
					</p>
				</div>
			)}
			{data && (
				<ScrollReveal>
					<div className="flex flex-col gap-1" data-slot="today-market-brief">
						{data.brief && (
							<div className="mx-2 mb-1 border-b border-(--color-border-subtle) pb-2">
								<div className="flex items-start justify-between gap-2">
									<div>
										<p className="text-xs uppercase tracking-[0.12em] text-(--color-foreground-tertiary)">
											Daily Brief
										</p>
										<p className="mt-0.5 text-sm font-medium text-(--color-foreground)">{data.brief.regimeLabel}</p>
									</div>
									<span className="rounded-full border border-(--color-border-subtle) px-2 py-0.5 text-xs text-(--color-foreground-secondary)">
										{data.brief.statusLabel}
									</span>
								</div>
								<div className="mt-2">
									<p className="text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
										今日变化与驱动
									</p>
									{data.brief.drivers.length === 0 ? (
										<p className="mt-1 text-xs text-(--color-foreground-tertiary)">没有足够证据形成 driver 排序</p>
									) : (
										<ul className="mt-1 space-y-1">
											{data.brief.drivers.slice(0, 3).map((driver) => (
												<li key={`${driver.category}:${driver.name}`} className="flex justify-between gap-2 text-xs">
													<span className="truncate text-(--color-foreground-secondary)">
														{DRIVER_LABELS[driver.name] ?? driver.name}
													</span>
													<span className="shrink-0 font-data text-(--color-foreground-tertiary)">
														{DIRECTION_LABELS[driver.direction]} {driver.contribution > 0 ? "+" : ""}
														{driver.contribution.toFixed(2)}
													</span>
												</li>
											))}
										</ul>
									)}
								</div>
							</div>
						)}
						{data.metrics.map((metric) => (
							<div
								key={metric.label}
								className="flex items-center justify-between rounded-[var(--radius-sm)] px-2 py-1 transition-colors hover:bg-(--color-interaction-hover-subtle-bg) border-b border-dashed border-(--color-border-subtle) last:border-b-0"
							>
								<span className="text-xs text-(--color-foreground-tertiary) uppercase tracking-[0.02em]">
									{metric.label}
								</span>
								<span
									className={`flex items-center gap-1.5 font-data text-xs tabular-nums ${changeTextColor(metric.change)}`}
								>
									{metric.value}
									{metric.change && <span>{metric.change}</span>}
									{metric.sparkline && metric.sparkline.length >= 2 && (
										<Sparkline data={metric.sparkline} color={changeToColor(metric.change)} width={48} height={16} />
									)}
								</span>
							</div>
						))}
						{data.brief && (
							<div className="mx-2 mt-1 border-t border-(--color-border-subtle) pt-2 text-xs text-(--color-foreground-tertiary)">
								<p>
									证据 {data.brief.evidenceRefs.length} · 快照 {data.brief.sourceSnapshotIds.length}
								</p>
								<p className="mt-0.5 truncate" title={data.brief.knowledgeCutoff}>
									Knowledge cutoff · {new Date(data.brief.knowledgeCutoff).toLocaleString("zh-CN")}
								</p>
								{data.brief.riskItems.length > 0 && (
									<div className="mt-2 border-l-2 border-(--color-risk-high-border) pl-2">
										<p className="font-medium text-(--color-foreground-secondary)">风险与缺口</p>
										{data.brief.riskItems.slice(0, 2).map((item) => (
											<p key={item} className="mt-0.5 text-(--color-foreground-tertiary)">
												{item}
											</p>
										))}
									</div>
								)}
							</div>
						)}
					</div>
				</ScrollReveal>
			)}
		</ContextSection>
	);
}
