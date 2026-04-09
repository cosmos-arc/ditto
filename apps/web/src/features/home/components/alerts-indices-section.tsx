import { useHomeAlerts, useMarketIndices } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { AlertRow } from "@/components/indicator/alert-row/alert-row";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { TrendDirection } from "@/types";

function formatTime(isoString: string): string {
	const date = new Date(isoString);
	return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export function AlertsAndIndicesSection() {
	const {
		data: alertsData,
		isLoading: alertsLoading,
		isError: alertsError,
		refetch: refetchAlerts,
	} = useHomeAlerts();

	const {
		data: indicesData,
		isLoading: indicesLoading,
	} = useMarketIndices();

	return (
		<div className="grid grid-cols-2 gap-4">
			<ContextSection title="全局告警" count={alertsData?.alerts.length}>
				{alertsLoading && <LoadingSkeleton variant="table" rows={3} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "告警加载失败",
						onRetry: () => void refetchAlerts(),
					}}
				>
					{alertsData && (
						<div className="space-y-1">
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
			</ContextSection>

			<ContextSection title="市场指数">
				{indicesLoading && <LoadingSkeleton variant="table" rows={5} />}
				{indicesData && (
					<div className="space-y-1">
						{indicesData.indices.map((index) => (
							<div
								key={index.code}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-surface-hover)"
							>
								<div className="flex items-center gap-2">
									<span className="font-medium">{index.name}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">
										{index.code}
									</span>
								</div>
								<div className="flex items-center gap-3">
									<span>{index.price.toLocaleString()}</span>
									<span
										className={
											index.dir === "up"
												? "text-(--color-status-success)"
												: "text-(--color-status-error)"
										}
									>
										{index.change >= 0 ? "+" : ""}
										{index.changePercent.toFixed(2)}%
									</span>
								</div>
							</div>
						))}
					</div>
				)}
			</ContextSection>
		</div>
	);
}
