import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { AlertRow } from "@/components/indicator/alert-row/alert-row";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useHomeAlerts } from "../hooks";

/**
 * GlobalAlertsSection — sidebar "全局预警" section.
 * Matches prototype .context-section with .alert-row items.
 */
export function GlobalAlertsSection() {
	const { data: alertsData, isLoading, refetch } = useHomeAlerts();

	return (
		<ContextSection
			title="全局预警"
			count={alertsData?.alerts.length}
			defaultOpen
			data-info-level="l1"
			data-info-unit="global-alerts"
			className="[&_[data-slot=context-section-header]>span:first-child]:ml-2 [&_[data-slot=context-section-header]>span:first-child]:pl-2.5"
		>
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "告警加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{alertsData && (
					<div className="flex flex-col">
						{alertsData.alerts.length === 0 && (
							<p className="px-3 py-3 text-xs text-(--color-foreground-tertiary)">当前决策快照没有阻断告警</p>
						)}
						{alertsData.alerts.map((alert) => (
							<AlertRow key={alert.id} severity={alert.severity} title={alert.title} time={alert.time} />
						))}
					</div>
				)}
			</DittoErrorBoundary>
			{alertsData && alertsData.alerts.length > 0 && (
				<div className="px-3 pb-2">
					<button
						type="button"
						className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
					>
						查看全部预警 →
					</button>
				</div>
			)}
		</ContextSection>
	);
}
