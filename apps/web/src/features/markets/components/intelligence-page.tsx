import { AnalyticalLayout } from "@/features/shell";
import { IntelligenceFlowView } from "./intelligence-flow-view";
import { IntelligenceMacroView } from "./intelligence-macro-view";
import { IntelligenceFundamentalsView } from "./intelligence-fundamentals-view";

export function IntelligencePage() {
	return (
		<AnalyticalLayout
			main={
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)] overflow-y-auto h-full">
					<IntelligenceFlowView />
					<div className="grid grid-cols-2 gap-[var(--density-gutter)]">
						<IntelligenceMacroView />
						<IntelligenceFundamentalsView />
					</div>
				</div>
			}
		/>
	);
}
