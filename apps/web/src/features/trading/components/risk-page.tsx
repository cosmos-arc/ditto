import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { RiskScopeStrip } from "./risk-scope-strip";
import { RiskExposureSummary } from "./risk-exposure-summary";

export function RiskPage() {
	return (
		<>
		<AnalyticalLayout
			className="pb-(--height-status-bar)"
			strip={<RiskScopeStrip />}
			main={
				<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<RiskExposureSummary />
				</div>
			}
			analysis={
				<div className="border-t border-(--color-border-subtle) bg-(--color-surface-0) px-3 py-2">
					<span className="text-xs text-(--color-foreground-tertiary)">风控分析面板 · 待实现</span>
				</div>
			}
		/>
		<StatusBar />
		</>
	);
}
