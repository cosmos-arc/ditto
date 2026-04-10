import { StudioLayout } from "@/features/shell";
import { StrategyHeader } from "./strategy-header";
import { FactorBrowser } from "./factor-browser";
import { StrategyEditor } from "./strategy-editor";
import { StrategyInspector } from "./strategy-inspector";

export function StrategyPage() {
	return (
		<StudioLayout
			source={<FactorBrowser />}
			main={
				<div className="flex flex-col gap-(--section-gap)">
					<StrategyHeader id="strat-001" />
					<StrategyEditor id="strat-001" />
				</div>
			}
			inspector={<StrategyInspector id="strat-001" />}
		/>
	);
}
