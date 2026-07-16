import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { AlertRow } from "@/components/indicator/alert-row/alert-row";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { usePlatformAlerts } from "../hooks";

function formatTime(isoString: string): string {
	const date = new Date(isoString);
	return date.toLocaleTimeString("zh-CN", {
		hour: "2-digit",
		minute: "2-digit",
	});
}

export function AlertList() {
	const { data, isLoading, refetch } = usePlatformAlerts();

	const activeAlerts = data?.items.filter((a) => a.status === "active") ?? [];

	return (
		<ContextSection title="System Alerts" count={activeAlerts.length} data-info-level="l1" data-info-unit="alerts">
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "告警数据加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<div className="space-y-1">
						{activeAlerts.length === 0 ? (
							<p className="px-3 py-4 text-center text-sm text-(--color-foreground-tertiary)">暂无活跃告警</p>
						) : (
							activeAlerts.map((alert) => (
								<AlertRow
									key={alert.id}
									severity={alert.severity}
									title={alert.title}
									time={formatTime(alert.createdAt)}
								/>
							))
						)}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
