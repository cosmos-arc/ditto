import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { RegimeCurrentView } from "./regime-current-view";
import { RegimeHistoryList } from "./regime-history-list";
import { RegimeStrategyImpact } from "./regime-strategy-impact";

export function RegimePage() {
	return (
		<AnalyticalLayout
			main={
				<div className="flex h-full flex-col gap-(--section-gap) overflow-y-auto p-(--density-panel-padding)">
					<RegimeCurrentView />
					<RegimeHistoryList />
				</div>
			}
			activity={
				<Panel>
					<PanelHeader title="策略影响" />
					<PanelBody className="p-3">
						<RegimeStrategyImpact />
					</PanelBody>
				</Panel>
			}
		/>
	);
}
