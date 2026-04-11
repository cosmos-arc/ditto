import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { RiskScopeStrip } from "./risk-scope-strip";
import { RiskBreachesList } from "./risk-breaches-list";
import { RiskExposureSummary } from "./risk-exposure-summary";

export function RiskPage() {
	return (
		<AnalyticalLayout
			strip={<RiskScopeStrip />}
			main={
				<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<RiskExposureSummary />
				</div>
			}
			activity={
				<Panel>
					<PanelHeader title="风控告警" />
					<PanelBody className="p-3">
						<RiskBreachesList />
					</PanelBody>
				</Panel>
			}
		/>
	);
}
