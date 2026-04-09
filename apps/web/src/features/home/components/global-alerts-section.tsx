import { useHomeAlerts } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { AlertRow } from "@/components/indicator/alert-row/alert-row";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

function formatTime(isoString: string): string {
	const date = new Date(isoString);
	return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

/**
 * GlobalAlertsSection — sidebar "全局预警" section.
 * Matches prototype .context-section with .alert-row items.
 */
export function GlobalAlertsSection() {
	const {
		data: alertsData,
		isLoading,
		isError,
		refetch,
	} = useHomeAlerts();

	return (
		<ContextSection title="全局预警" count={alertsData?.alerts.length} defaultOpen>
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "告警加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{alertsData && (
					<div className="flex flex-col">
						{alertsData.alerts.map((alert) => (
							<AlertRow
								key={alert.id}
								severity={alert.severity}
								title={alert.title}
								time={formatTime(alert.time)}
							/>
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
