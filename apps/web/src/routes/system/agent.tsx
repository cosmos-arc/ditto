import { createFileRoute } from "@tanstack/react-router";
import {
	type AgentConsoleRouteSearch,
	type AgentConsoleSearch,
	parseAgentConsoleSearch as parseSearch,
} from "@/features/agent";
import { SystemAgentOpsPage } from "@/features/system";

export const parseAgentConsoleSearch = (search: Record<string, unknown>): AgentConsoleRouteSearch =>
	parseSearch(search, { allowedTabs: ["runs", "campaigns"], defaultTab: "runs" });

function SystemAgentOpsRoute() {
	const search = Route.useSearch();
	const navigate = Route.useNavigate();
	return (
		<SystemAgentOpsPage
			search={search}
			onSearchChange={(next: AgentConsoleSearch) => {
				void navigate({
					replace: true,
					search: {
						contextId: next.contextId,
						contextType: next.contextType,
						objective: next.objective,
						offset: next.offset ?? 0,
						selected: next.selected,
						sessionId: next.sessionId,
						sessionOffset: next.sessionOffset ?? 0,
						status: next.status,
						tab: next.tab === "campaigns" ? "campaigns" : "runs",
					},
				});
			}}
		/>
	);
}

export const Route = createFileRoute("/system/agent")({
	validateSearch: parseAgentConsoleSearch,
	component: SystemAgentOpsRoute,
	staticData: { title: "System Agent Ops" },
});
