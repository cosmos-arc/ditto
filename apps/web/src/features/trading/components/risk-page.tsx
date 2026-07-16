import { useState } from "react";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { StatusBadge } from "@/components/status";
import { AnalyticalLayout, OverlayProvider, StatusBar, useOverlayController } from "@/features/shell";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { BreachDetailContent } from "./risk-breach-detail";
import { RiskBreachesList } from "./risk-breaches-list";
import { RiskExposureSummary } from "./risk-exposure-summary";
import { RiskScopeStrip } from "./risk-scope-strip";

const RISK_BREACH_OVERLAY_ID = "risk.breach-detail";

export function RiskPage() {
	if (!shouldUsePrototypeMocks()) {
		return <RiskLiveEmptyPage />;
	}

	return (
		<OverlayProvider>
			<RiskPageContent />
		</OverlayProvider>
	);
}

function RiskLiveEmptyPage() {
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
						<StatusBadge label="prototype only" variant="idle" size="sm" />
						<span className="text-sm text-(--color-foreground-secondary)">Risk 数据待后端补齐</span>
					</div>
				}
				main={
					<div className="flex h-full flex-col justify-center gap-3 p-(--density-panel-padding)">
						<div data-info-level="l1" data-info-unit="risk-live-empty" className="flex max-w-xl flex-col gap-2">
							<StatusBadge label="V1a 未接 live" variant="idle" size="sm" />
							<p className="text-base font-medium text-(--color-foreground)">V1a 未接 live，数据待后端补齐</p>
							<p className="text-sm text-(--color-foreground-tertiary)">
								当前后端 Wave1 暂未暴露风险聚合接口，先保留页面结构与明确占位。
							</p>
						</div>
					</div>
				}
				analysis={
					<div
						data-info-level="l2"
						data-info-unit="risk-analysis-panel"
						className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2"
					>
						<span className="text-xs text-(--color-foreground-tertiary)">风控分析面板 · 待 live 接口补齐</span>
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
