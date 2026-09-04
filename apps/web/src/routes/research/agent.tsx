import { createFileRoute } from "@tanstack/react-router";
import { AgentConsolePage, type AgentConsoleSearch, parseAgentConsoleSearch } from "@/features/agent";

const validateResearchAgentSearch = (search: Record<string, unknown>) =>
	parseAgentConsoleSearch(search, { allowedTabs: ["runs", "campaigns"], defaultTab: "runs" });

function ResearchAgentLabRoute() {
	const search = Route.useSearch();
	const navigate = Route.useNavigate();
	return (
		<AgentConsolePage
			surface="research-lab"
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

export const Route = createFileRoute("/research/agent")({
	validateSearch: validateResearchAgentSearch,
	component: ResearchAgentLabRoute,
	staticData: { title: "Research Agent Lab" },
});
