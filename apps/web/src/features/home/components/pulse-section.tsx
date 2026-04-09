import { useHomePulse } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

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
			<div className="flex h-[var(--density-strip-height)] items-center gap-4 overflow-hidden bg-(--color-surface-strip) px-4 text-[10px] text-(--color-foreground-tertiary)">
				{/* 1. Time + Status */}
				<div className="flex items-center gap-1 whitespace-nowrap">
					<span className="inline-block size-1.5 animate-pulse rounded-full bg-(--color-system-healthy-fg)" />
					<span className="font-(--font-data)">{data?.date ?? "—"}</span>
					<span>·</span>
					<span>{data?.session === "continuous" ? "盘中交易" : data?.session === "pre" ? "盘前" : "已收盘"}</span>
				</div>

				<PulseSeparator />

				{/* 2. PnL */}
				<div className="flex items-center gap-1 whitespace-nowrap">
					<span>盈亏</span>
					<span className={`font-(--font-data) ${isPositive ? "text-(--color-market-up-fg)" : "text-(--color-market-down-fg)"}`}>
						{isPositive ? "+" : ""}{data?.pnlPercent ?? 0}%
					</span>
				</div>

				<PulseSeparator />

				{/* 3. Pending */}
				<div className="flex items-center gap-1 whitespace-nowrap">
					<span>待处理</span>
					<span className="font-(--font-data) text-(--color-foreground-secondary)">{data?.pendingActions ?? 0}</span>
				</div>

				<PulseSeparator />

				{/* 4. Running jobs */}
				<div className="flex items-center gap-1 whitespace-nowrap">
					<span>运行中</span>
					<span className="font-(--font-data) text-(--color-foreground-secondary)">{data?.runningJobs ?? 0}</span>
				</div>
			</div>
		</DittoErrorBoundary>
	);
}

function PulseSeparator() {
	return <div className="h-2.5 w-px bg-(--color-border-subtle)" />;
}
