import { OpsConsoleLayout, StatusBar } from "@/features/shell";
import { AgentFindingsList } from "./agent-findings-list";
import { AgentInspectorPanel } from "./agent-inspector-panel";

export function AgentsPage() {
	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar)"
				main={
					<div className="flex items-center justify-center p-(--density-panel-padding)">
						<AgentInspectorPanel planId="plan-001" />
					</div>
				}
				detail={
					<div className="h-full overflow-y-auto">
						<AgentFindingsList />
					</div>
				}
			/>
			<StatusBar />
		</>
	);
}
