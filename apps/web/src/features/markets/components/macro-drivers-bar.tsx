import { useMacroDrivers } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { Sparkline } from "@/components/data/sparkline/sparkline";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function MacroDriversBar() {
	const { data, isLoading, isError, refetch } = useMacroDrivers();

	return (
		<ContextSection title="宏观驱动">
			{isLoading && <LoadingSkeleton variant="metric" />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="flex gap-4">
						{data.indicators.map((indicator) => (
							<div
								key={indicator.name}
								className="flex flex-1 flex-col items-center gap-1 rounded-md bg-(--color-surface-base) p-2"
							>
								<span className="text-xs text-(--color-foreground-tertiary)">
									{indicator.name}
								</span>
								<span className="text-sm font-medium">
									{indicator.value.toLocaleString()}
								</span>
								<span
									className={
										indicator.change >= 0
											? "text-(--color-status-success)"
											: "text-(--color-status-error)"
									}
								>
									{indicator.change >= 0 ? "+" : ""}
									{indicator.change.toFixed(2)}
								</span>
								<Sparkline
									data={indicator.sparkline}
									color={
										indicator.change >= 0
											? "var(--color-status-success)"
											: "var(--color-status-error)"
									}
									width={120}
									height={32}
								/>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
