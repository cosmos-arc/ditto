import { useState } from "react";
import {
	AnalyticalLayout,
	OverlayProvider,
	StatusBar,
	useOverlayController,
} from "@/features/shell";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { RiskScopeStrip } from "./risk-scope-strip";
import { RiskExposureSummary } from "./risk-exposure-summary";
import { RiskBreachesList } from "./risk-breaches-list";
import { BreachDetailContent } from "./risk-breach-detail";

const RISK_BREACH_OVERLAY_ID = "risk.breach-detail";

export function RiskPage() {
	return (
		<OverlayProvider>
			<RiskPageContent />
		</OverlayProvider>
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
					<div data-info-level="l2" data-info-unit="risk-analysis-panel" className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
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
