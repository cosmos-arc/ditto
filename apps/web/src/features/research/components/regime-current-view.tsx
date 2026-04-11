import { useRegimeCurrent } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const STATE_VARIANT_MAP: Record<string, "regime-on" | "regime-off" | "regime-mixed"> = {
	risk_on: "regime-on",
	risk_off: "regime-off",
	volatile: "regime-mixed",
	transition: "regime-mixed",
};

const STATE_LABEL_MAP: Record<string, string> = {
	risk_on: "Risk On",
	risk_off: "Risk Off",
	volatile: "Volatile",
	transition: "Transition",
};

export function RegimeCurrentView() {
	const { data, isLoading, refetch } = useRegimeCurrent();

	if (isLoading) {
		return (
			<ContextSection title="当前状态">
				<LoadingSkeleton variant="panel" rows={4} />
			</ContextSection>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<ContextSection title="当前状态">
				{data && (
					<div className="flex flex-col gap-3">
						<div className="flex items-center gap-3">
							<StatusBadge
								variant={STATE_VARIANT_MAP[data.state] ?? "regime-mixed"}
								label={data.state}
							/>
							<span className="text-(--color-foreground-secondary) text-sm">
								置信度 <strong>{Math.round(data.confidence * 100)}%</strong>
							</span>
							<span className="text-(--color-foreground-tertiary) text-xs">
								持续 {data.duration} 天
							</span>
						</div>
						<div className="grid grid-cols-2 gap-2">
							{data.keyIndicators.map((ind) => (
								<div key={ind.name} className="flex flex-col gap-0.5">
									<span className="text-xs text-(--color-foreground-tertiary)">
										{ind.name}
									</span>
									<span className="text-sm font-data text-(--color-foreground)">
										{ind.value}
									</span>
									<span className="text-xs text-(--color-foreground-tertiary)">
										{ind.description}
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
