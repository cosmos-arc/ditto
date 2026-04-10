import { StudioLayout } from "@/features/shell";
import { AgentPlansList } from "./agent-plans-list";
import { AgentFindingsList } from "./agent-findings-list";
import { AgentInspectorPanel } from "./agent-inspector-panel";

export function AgentsPage() {
	return (
		<StudioLayout
			source={
				<div className="h-full overflow-y-auto border-r border-(--color-border-subtle)">
					<AgentPlansList />
				</div>
			}
			main={
				<div className="flex items-center justify-center p-(--density-panel-padding)">
					<AgentInspectorPanel planId="plan-001" />
				</div>
			}
			inspector={
				<div className="h-full overflow-y-auto border-l border-(--color-border-subtle)">
					<AgentFindingsList />
				</div>
			}
		/>
	);
}
