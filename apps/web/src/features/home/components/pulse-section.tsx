import { useHomePulse } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { ScrollReveal } from "@/components/ui/scroll-reveal";

/**
 * PulseSection — thin operational status strip.
 * Matches prototype .shell-pulse: 32px height, surface-strip bg,
 * 10px font, horizontal flex with separators.
 */
export function PulseSection() {
	const { data, isLoading, isError, refetch } = useHomePulse();

	if (isLoading) {
		return (
			<div className="flex h-[var(--density-strip-height)] items-center gap-4 bg-(--color-surface-strip) px-4">
				{Array.from({ length: 3 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" className="h-4 w-24" />
				))}
			</div>
		);
	}

	const isPositive = (data?.pnlPercent ?? 0) >= 0;

	return (
		<DittoErrorBoundary
			fallbackProps={{
				title: "脉动数据加载失败",
				onRetry: () => void refetch(),
			}}
		>
			<ScrollReveal>
				<div data-slot="pulse-strip" className="flex h-[var(--density-strip-height)] items-center gap-4 overflow-hidden bg-(--color-surface-strip) px-4 text-xs text-(--color-foreground-tertiary)">
					{/* 1. Time + Status */}
					<div className="flex items-center gap-1 whitespace-nowrap">
						<span className="inline-block size-1.5 rounded-full bg-(--color-system-healthy-fg) animate-[dot-live-pulse_3s_ease-in-out_infinite]" />
						<span className="font-data">{data?.date ?? "—"}</span>
						<span>·</span>
						<span>{data?.session === "continuous" ? "盘中交易" : data?.session === "pre" ? "盘前" : "已收盘"}</span>
					</div>

					<PulseSeparator />

					{/* 2. PnL */}
					<div className="flex items-center gap-1 whitespace-nowrap">
						<span>盈亏</span>
						<span className={`font-data ${isPositive ? "text-(--color-market-up-fg)" : "text-(--color-market-down-fg)"}`}>
							{isPositive ? "+" : ""}{data?.pnlPercent ?? 0}%
						</span>
					</div>

					<PulseSeparator />

					{/* 3. Risk — 风险等级 */}
					<div className="flex items-center gap-1 whitespace-nowrap">
						<span>风险</span>
						<span className="font-data text-(--color-risk-high-fg)">中等</span>
					</div>

					<PulseSeparator />

					{/* 4. Regime — 市场环境 */}
					<div className="flex items-center gap-1 whitespace-nowrap">
						<span className="rounded-[10px] bg-(--color-surface-strip) px-2 py-px text-xs tracking-[0.02em] text-(--color-foreground-secondary)">温和风险偏好</span>
					</div>

					<PulseSeparator />

					{/* 5. Pending + Jobs */}
					<div className="flex items-center gap-1 whitespace-nowrap">
						<span>待处理</span>
						<span className="font-data text-(--color-foreground-secondary)">{data?.pendingActions ?? 0}</span>
						<span className="ml-2">运行中</span>
						<span className="font-data text-(--color-foreground-secondary)">{data?.runningJobs ?? 0}</span>
					</div>
				</div>
			</ScrollReveal>
		</DittoErrorBoundary>
	);
}

function PulseSeparator() {
	return <div className="h-2.5 w-px bg-(--color-border-subtle)" />;
}
