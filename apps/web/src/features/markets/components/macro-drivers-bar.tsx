import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Sparkline } from "@/components/data/sparkline/sparkline";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useMacroDrivers } from "../hooks";

export function MacroDriversBar() {
	const { data, isLoading, refetch } = useMacroDrivers();

	return (
		<ContextSection title="宏观驱动" data-info-level="l2" data-info-unit="macro-drivers">
			{isLoading && <LoadingSkeleton variant="metric" />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="flex gap-4">
						{data.indicators.map((indicator) => (
							<div
								key={indicator.name}
								className="flex flex-1 flex-col items-center gap-1 rounded-md bg-(--color-surface-1) p-2"
							>
								<span className="text-xs text-(--color-foreground-tertiary)">{indicator.name}</span>
								<span className="text-sm font-medium">{indicator.value.toLocaleString()}</span>
								<span
									className={indicator.change >= 0 ? "text-(--color-system-healthy)" : "text-(--color-system-down)"}
								>
									{indicator.change >= 0 ? "+" : ""}
									{indicator.change.toFixed(2)}
								</span>
								<Sparkline
									data={indicator.sparkline.map((point) => point.value)}
									color={indicator.change >= 0 ? "up" : "down"}
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
