import { CatalogLayout } from "@/features/shell";
import { AgentPlansList } from "./agent-plans-list";
import { AgentFindingsList } from "./agent-findings-list";

export function AgentsPage() {
	return (
		<CatalogLayout
			main={
				<div className="grid grid-cols-2 gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<AgentPlansList />
					<AgentFindingsList />
				</div>
			}
		/>
	);
}
