import { createFileRoute } from "@tanstack/react-router";
import type { AgentConsoleSearch, AgentTab } from "@/features/agent";
import { PlatformAgentsPage } from "@/features/platform";

export interface AgentConsoleRouteSearch {
	readonly contextId: string | undefined;
	readonly contextType: string | undefined;
	readonly objective: string | undefined;
	readonly offset: number;
	readonly selected: string | undefined;
	readonly sessionId: string | undefined;
	readonly sessionOffset: number;
	readonly status: string | undefined;
	readonly tab: AgentTab;
}

function optionalString(value: unknown): string | undefined {
	return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

export function parseAgentConsoleSearch(search: Record<string, unknown>): AgentConsoleRouteSearch {
	const rawOffset =
		typeof search.offset === "number" ? search.offset : Number.parseInt(String(search.offset ?? "0"), 10);
	const rawSessionOffset =
		typeof search.sessionOffset === "number"
			? search.sessionOffset
			: Number.parseInt(String(search.sessionOffset ?? "0"), 10);
	return {
		contextId: optionalString(search.contextId),
		contextType: optionalString(search.contextType),
		objective: optionalString(search.objective),
		offset: Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0,
		selected: optionalString(search.selected),
		sessionId: optionalString(search.sessionId),
		sessionOffset: Number.isFinite(rawSessionOffset) && rawSessionOffset > 0 ? Math.floor(rawSessionOffset) : 0,
		status: optionalString(search.status),
		tab: search.tab === "campaigns" || search.tab === "approvals" ? search.tab : "runs",
	};
}

function AgentConsoleRoute() {
	const search = Route.useSearch();
	const navigate = Route.useNavigate();
	return (
		<PlatformAgentsPage
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
						tab: next.tab ?? "runs",
					},
				});
			}}
		/>
	);
}

export const Route = createFileRoute("/platform/agents")({
	validateSearch: parseAgentConsoleSearch,
	component: AgentConsoleRoute,
	staticData: { title: "Agent Console" },
});
