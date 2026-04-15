import { useState } from "react";
import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { RiskScopeStrip } from "./risk-scope-strip";
import { RiskExposureSummary } from "./risk-exposure-summary";
import { RiskBreachesList } from "./risk-breaches-list";
import { BreachDetailContent } from "./risk-breach-detail";

export function RiskPage() {
	const [selectedBreachId, setSelectedBreachId] = useState<string | null>(null);

	return (
		<>
			<AnalyticalLayout
				className="pb-(--height-status-bar)"
				strip={<RiskScopeStrip />}
				main={
					<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
						<RiskExposureSummary />
						<RiskBreachesList onSelectBreach={setSelectedBreachId} />
					</div>
				}
				analysis={
					<div className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
						<span className="text-xs text-(--color-foreground-tertiary)">风控分析面板 · 待实现</span>
					</div>
				}
			/>
			<StatusBar />
			<Drawer
				open={selectedBreachId !== null}
				onClose={() => setSelectedBreachId(null)}
				title="告警详情"
			>
				{selectedBreachId && <BreachDetailContent breachId={selectedBreachId} />}
			</Drawer>
		</>
	);
}
