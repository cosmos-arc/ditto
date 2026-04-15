import { useRiskSummary, useSignalsQueue, useOrdersSummary } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function RiskAlertsBlock() {
	const { data: risk, isLoading: riskLoading, isError: riskError, refetch: riskRefetch } = useRiskSummary();
	const { data: signals } = useSignalsQueue();
	const { data: orders } = useOrdersSummary();

	return (
		<ContextSection title="风控 & 预警" data-info-level="l1" data-info-unit="risk-alerts">
			{riskLoading && <LoadingSkeleton variant="metric" />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void riskRefetch() }}>
				{risk && (
					<div className="flex flex-col gap-3">
						<div className="grid grid-cols-4 gap-3">
							<Metric
								variant="strip"
								label="VaR"
								value={`${risk.var}%`}
								trend={risk.var >= 0 ? "up" : "down"}
							/>
							<Metric
								variant="strip"
								label="最大回撤"
								value={`${risk.maxDD}%`}
								trend="down"
							/>
							<Metric variant="strip" label="Beta" value={risk.beta.toFixed(2)} />
							<Metric
								variant="strip"
								label="总敞口"
								value={`${risk.grossExposure}%`}
								trend={risk.grossExposure > 150 ? "down" : "up"}
							/>
						</div>
						<div className="flex gap-4 text-sm text-(--color-foreground-tertiary)">
							{signals && (
								<span data-info-level="l2" data-info-unit="risk-alerts-signals">
									信号: <strong>{signals.pending} 待复核</strong> / {signals.confirmed} 已确认 / {signals.ordered} 已转单
								</span>
							)}
							{orders && (
								<span data-info-level="l2" data-info-unit="risk-alerts-orders">
									订单: <strong>{orders.filled} 已成交</strong> / {orders.pending} 待提交 / {orders.submitted} 已提交
								</span>
							)}
						</div>
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
