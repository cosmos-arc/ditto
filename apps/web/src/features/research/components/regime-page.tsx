import { AnalyticalLayout } from "@/features/shell";
import { RegimeCurrentView } from "./regime-current-view";
import { RegimeHistoryList } from "./regime-history-list";
import { RegimeStrategyImpact } from "./regime-strategy-impact";

export function RegimePage() {
	return (
		<AnalyticalLayout
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)] overflow-y-auto h-full">
					<RegimeCurrentView />
					<div className="grid grid-cols-2 gap-4">
						<RegimeHistoryList />
						<RegimeStrategyImpact />
					</div>
				</div>
			}
		/>
	);
}
