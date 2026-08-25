import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { AnalyticalLayout, OverlayProvider, StatusBar, useOverlayController } from "@/features/shell";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV3 } from "../hooks";
import { DecisionBriefing } from "./decision-briefing";
import { BreachDetailContent } from "./risk-breach-detail";
import { RiskBreachesList } from "./risk-breaches-list";
import { RiskDecisionCenter } from "./risk-decision-center";
import { RiskExposureSummary } from "./risk-exposure-summary";
import { RiskScopeStrip } from "./risk-scope-strip";

const RISK_BREACH_OVERLAY_ID = "risk.breach-detail";

export function RiskPage() {
	if (!shouldUsePrototypeMocks()) {
		return <RiskLivePage />;
	}

	return (
		<OverlayProvider>
			<RiskPageContent />
		</OverlayProvider>
	);
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

function RiskPageContent() {
	const [selectedBreachId, setSelectedBreachId] = useState<string | null>(null);
	const { activeOverlayId, closeOverlay, openOverlay } = useOverlayController();

	function handleSelectBreach(breachId: string) {
		setSelectedBreachId(breachId);
		openOverlay(RISK_BREACH_OVERLAY_ID);
	}

	function handleCloseBreachDetail() {
		closeOverlay();
		setSelectedBreachId(null);
	}

	return (
		<>
			<AnalyticalLayout
				className="pb-(--height-status-bar)"
				strip={<RiskScopeStrip />}
				main={
					<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
						<RiskExposureSummary />
						<RiskBreachesList onSelectBreach={handleSelectBreach} />
					</div>
				}
				analysis={
					<div
						data-info-level="l2"
						data-info-unit="risk-analysis-panel"
						className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2"
					>
						<span className="text-xs text-(--color-foreground-tertiary)">风控分析面板 · 待实现</span>
					</div>
				}
			/>
			<StatusBar />
			<Drawer
				open={activeOverlayId === RISK_BREACH_OVERLAY_ID && selectedBreachId !== null}
				onClose={handleCloseBreachDetail}
				title="告警详情"
			>
				<div data-info-level="l2" data-info-unit="breach-detail">
					{selectedBreachId && <BreachDetailContent breachId={selectedBreachId} />}
				</div>
			</Drawer>
		</>
	);
}
