import { AnalyticalLayout } from "@/features/shell";
import { RiskBreachesList } from "./risk-breaches-list";
import { RiskExposureSummary } from "./risk-exposure-summary";

export function RiskPage() {
	return (
		<AnalyticalLayout
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<RiskBreachesList />
					<RiskExposureSummary />
				</div>
			}
		/>
	);
}
