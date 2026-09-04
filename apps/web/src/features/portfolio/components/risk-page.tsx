import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV3 } from "../hooks";
import { DecisionBriefing } from "./decision-briefing";
import { RiskDecisionCenter } from "./risk-decision-center";
import { RiskMockWorkspace } from "./risk-workspace";

export function RiskPage() {
	if (!shouldUsePrototypeMocks()) {
		return <RiskLivePage />;
	}

	return <RiskMockWorkspace />;
}

function RiskLivePage() {
	const { data, isLoading, isError, refetch } = useDailyDecisionV3();

	return (
		<>
			<AnalyticalLayout
				className="pb-(--height-status-bar)"
				strip={
					<div
						data-info-level="l1"
						data-info-unit="risk-scope-strip"
						className="flex h-9 items-center gap-3 px-4 py-1.5"
					>
						<StatusBadge
							label={data?.readiness.status ?? (isError ? "unavailable" : "loading")}
							variant={
								data?.readiness.status === "ready"
									? "healthy"
									: data?.readiness.status === "review"
										? "warning"
										: "critical"
							}
							size="sm"
						/>
						<span className="font-data text-sm text-(--color-foreground-secondary)">
							{data
								? `${data.identity.strategyId} / ${data.identity.accountId ?? "account unselected"}`
								: "Daily Decision V3"}
						</span>
					</div>
				}
				main={
					<div className="flex h-full flex-col gap-(--section-gap) overflow-y-auto p-(--density-panel-padding)">
						{isLoading && (
							<div role="status" aria-label="风险决策加载中">
								<LoadingSkeleton variant="panel" rows={6} />
							</div>
						)}
						{isError && (
							<div
								role="alert"
								className="flex items-center justify-between gap-3 rounded-(--radius-sm) border border-(--color-risk-critical-fg) p-3"
							>
								<span className="text-sm text-(--color-foreground-secondary)">
									风险决策加载失败，未使用原型数据替代。
								</span>
								<Button variant="outline" size="sm" onClick={() => void refetch()}>
									重试
								</Button>
							</div>
						)}
						{!isLoading && !isError && !data && (
							<div role="status" className="rounded-(--radius-sm) border border-(--color-border-subtle) p-4 text-sm">
								暂无风险决策
							</div>
						)}
						{data && (
							<>
								<RiskDecisionCenter decision={data} />
								<DecisionBriefing decision={data} />
							</>
						)}
					</div>
				}
				analysis={
					<div
						data-info-level="l2"
						data-info-unit="risk-analysis-panel"
						className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2"
					>
						<span className="text-xs text-(--color-foreground-tertiary)">
							PIT publication cutoff · {data?.provenance.publicationCutoff ?? "unavailable"}
						</span>
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
