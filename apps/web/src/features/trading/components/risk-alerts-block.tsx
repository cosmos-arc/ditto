import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2, useOrdersSummary, useRiskSummary, useSignalsQueue } from "../hooks";

function PrototypeRiskAlertsBlock() {
	const { data: risk, isLoading: riskLoading, refetch: riskRefetch } = useRiskSummary();
	const { data: signals } = useSignalsQueue();
	const { data: orders } = useOrdersSummary();

	return (
		<ContextSection title="风控 & 预警" data-info-level="l1" data-info-unit="risk-alerts">
			{riskLoading && <LoadingSkeleton variant="metric" />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void riskRefetch() }}>
				{risk && (
					<div className="flex flex-col gap-3">
						<div className="grid grid-cols-4 gap-3">
							<Metric variant="strip" label="VaR" value={`${risk.var}%`} trend={risk.var >= 0 ? "up" : "down"} />
							<Metric variant="strip" label="最大回撤" value={`${risk.maxDD}%`} trend="down" />
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
									信号: <strong>{signals.pending} 待复核</strong> / {signals.confirmed} 已确认 / {signals.ordered}{" "}
									已转单
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

function LiveRiskAlertsBlock() {
	const { data, isLoading, isError, refetch } = useDailyDecisionV2();
	const riskEvidence = data?.run_package.risk_evidence ?? [];
	const readinessReasons = data?.readiness.reason_codes ?? [];

	return (
		<ContextSection title="风控 & 预警" data-info-level="l1" data-info-unit="risk-alerts">
			{isLoading && (
				<div role="status" aria-label="风控证据加载中">
					<LoadingSkeleton variant="metric" />
				</div>
			)}
			{isError && (
				<div
					role="alert"
					className="flex flex-col items-start gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
				>
					<span>风控证据加载失败</span>
					<Button variant="outline" size="sm" onClick={() => void refetch()}>
						重试
					</Button>
				</div>
			)}
			{!isLoading && !isError && data && (
				<div className="flex flex-col gap-3 py-2">
					<div className="flex flex-wrap items-center gap-2">
						<StatusBadge
							label={data.readiness.status}
							variant={
								data.readiness.status === "ready"
									? "healthy"
									: data.readiness.status === "review"
										? "warning"
										: "critical"
							}
							size="sm"
						/>
						<span className="text-xs text-(--color-foreground-tertiary)">仅展示 Daily Decision 后端证据</span>
					</div>
					<div className="grid gap-3 sm:grid-cols-2">
						<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
							<h3 className="text-xs font-medium text-(--color-foreground)">Readiness reason codes</h3>
							<ul className="mt-2 flex flex-col gap-1 font-data text-xs text-(--color-foreground-secondary)">
								{readinessReasons.length > 0 ? (
									readinessReasons.map((reason) => <li key={reason}>{reason}</li>)
								) : (
									<li>—</li>
								)}
							</ul>
						</section>
						<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
							<h3 className="text-xs font-medium text-(--color-foreground)">Package risk evidence</h3>
							<ul className="mt-2 flex flex-col gap-1 font-data text-xs text-(--color-foreground-secondary)">
								{riskEvidence.length > 0 ? (
									riskEvidence.map((evidence) => <li key={evidence}>{evidence}</li>)
								) : (
									<li>无额外风险证据</li>
								)}
							</ul>
						</section>
					</div>
				</div>
			)}
		</ContextSection>
	);
}

export function RiskAlertsBlock() {
	return shouldUsePrototypeMocks() ? <PrototypeRiskAlertsBlock /> : <LiveRiskAlertsBlock />;
}
