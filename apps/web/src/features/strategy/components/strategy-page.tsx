import { StudioLayout, StatusBar } from "@/features/shell";
import { StrategyHeader } from "./strategy-header";
import { FactorBrowser } from "./factor-browser";
import { StrategyEditor } from "./strategy-editor";
import { StrategyInspector } from "./strategy-inspector";
import { StudioModeBar } from "./studio-mode-bar";

const STUDIO_MODES = [
	{ id: "form", label: "Form Builder" },
	{ id: "code", label: "Code Editor" },
] as const;

const STUDIO_BREADCRUMBS = ["研究", "策略", "多因子动量策略 v2.3"] as const;

export function StrategyPage() {
	return (
		<>
			<StudioLayout
				className="pb-(--height-status-bar)"
				modes={
					<div data-info-level="l1" data-info-unit="studio-mode-bar">
						<StudioModeBar modes={STUDIO_MODES} breadcrumbs={STUDIO_BREADCRUMBS} />
					</div>
				}
				source={
					<div data-info-level="l1" data-info-unit="factor-browser">
						<FactorBrowser />
					</div>
				}
				main={
					<div className="flex flex-col gap-(--section-gap)">
						<div data-info-level="l1" data-info-unit="strategy-header">
							<StrategyHeader id="strat-001" />
						</div>
						<div data-info-level="l1" data-info-unit="strategy-code">
							<StrategyEditor id="strat-001" />
						</div>
					</div>
				}
				inspector={
					<div data-info-level="l2" data-info-unit="strategy-inspector">
						<StrategyInspector id="strat-001" />
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
