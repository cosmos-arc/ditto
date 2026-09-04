import { createFileRoute } from "@tanstack/react-router";
import { AgentConsolePage, type AgentConsoleSearch, parseAgentConsoleSearch } from "@/features/agent";

const validateApprovalSearch = (search: Record<string, unknown>) =>
	parseAgentConsoleSearch(search, { allowedTabs: ["approvals"], defaultTab: "approvals" });

function ApprovalInboxRoute() {
	const search = Route.useSearch();
	const navigate = Route.useNavigate();
	return (
		<AgentConsolePage
			surface="approval-inbox"
			search={search}
			onSearchChange={(next: AgentConsoleSearch) => {
				void navigate({
					replace: true,
					search: {
						contextId: undefined,
						contextType: undefined,
						objective: undefined,
						offset: next.offset ?? 0,
						selected: next.selected,
						sessionId: undefined,
						sessionOffset: 0,
						status: next.status,
						tab: "approvals",
					},
				});
			}}
		/>
	);
}

export const Route = createFileRoute("/system/approvals")({
	validateSearch: validateApprovalSearch,
	component: ApprovalInboxRoute,
	staticData: { title: "Agent Approvals" },
});
