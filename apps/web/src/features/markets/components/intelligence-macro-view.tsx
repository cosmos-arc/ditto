import { useIntelligenceMacro } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function IntelligenceMacroView() {
	const { data, isLoading, refetch } = useIntelligenceMacro();

	if (isLoading) {
		return (
			<ContextSection title="宏观指标">
				<LoadingSkeleton variant="panel" rows={4} />
			</ContextSection>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<ContextSection title="宏观指标">
				{data && (
					<div className="flex flex-col gap-3">
						<div className="grid grid-cols-2 gap-2">
							{data.indicators.map((ind) => (
								<div key={ind.name} className="flex flex-col gap-0.5">
									<span className="text-xs text-(--color-foreground-tertiary)">
										{ind.name}
									</span>
									<span
										className={`text-sm font-data ${ind.change >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}`}
									>
										{ind.value}
										{ind.unit}
										<span className="text-xs ml-1">
											({ind.change > 0 ? "+" : ""}{ind.change})
										</span>
									</span>
								</div>
							))}
						</div>
						<div className="flex flex-col gap-1">
							<span className="text-xs text-(--color-foreground-tertiary)">经济日历</span>
							{data.calendar.slice(0, 4).map((ev, i) => (
								<div
									key={`${ev.date}-${ev.event}-${i}`}
									className="flex items-center justify-between py-1 border-b border-(--color-border) last:border-b-0"
								>
									<div className="flex flex-col gap-0.5 min-w-0">
										<span className="text-sm text-(--color-foreground) truncate">
											{ev.country} {ev.event}
										</span>
										<span className="text-xs text-(--color-foreground-tertiary)">
											{ev.date} {ev.time}
										</span>
									</div>
									<span
										className={`text-xs font-data shrink-0 ${ev.importance === "high" ? "text-(--color-status-warning)" : "text-(--color-foreground-tertiary)"}`}
									>
										{ev.importance === "high" ? "高" : "中"}
									</span>
								</div>
							))}
						</div>
					</div>
				)}
			</ContextSection>
		</DittoErrorBoundary>
	);
}
