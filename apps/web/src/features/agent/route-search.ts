import type { AgentTab } from "./types";

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

interface AgentRouteSearchPolicy {
	readonly allowedTabs?: readonly AgentTab[];
	readonly defaultTab?: AgentTab;
}

function optionalString(value: unknown): string | undefined {
	return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

export function parseAgentConsoleSearch(
	search: Record<string, unknown>,
	policy: AgentRouteSearchPolicy = {},
): AgentConsoleRouteSearch {
	const allowedTabs = policy.allowedTabs ?? (["runs", "campaigns", "approvals"] as const);
	const defaultTab = policy.defaultTab ?? "runs";
	const rawOffset =
		typeof search["offset"] === "number" ? search["offset"] : Number.parseInt(String(search["offset"] ?? "0"), 10);
	const rawSessionOffset =
		typeof search["sessionOffset"] === "number"
			? search["sessionOffset"]
			: Number.parseInt(String(search["sessionOffset"] ?? "0"), 10);
	const requestedTab = search["tab"] === "campaigns" || search["tab"] === "approvals" ? search["tab"] : "runs";
	return {
		contextId: optionalString(search["contextId"]),
		contextType: optionalString(search["contextType"]),
		objective: optionalString(search["objective"]),
		offset: Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0,
		selected: optionalString(search["selected"]),
		sessionId: optionalString(search["sessionId"]),
		sessionOffset: Number.isFinite(rawSessionOffset) && rawSessionOffset > 0 ? Math.floor(rawSessionOffset) : 0,
		status: optionalString(search["status"]),
		tab: allowedTabs.includes(requestedTab) ? requestedTab : defaultTab,
	};
}
