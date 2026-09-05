import { AgentConsolePage, type AgentConsoleSearch } from "@/features/agent";

export function SystemAgentOpsPage({
	initialSearch,
	onSearchChange,
	search,
}: {
	readonly initialSearch?: AgentConsoleSearch;
	readonly onSearchChange?: (search: AgentConsoleSearch) => void;
	readonly search?: AgentConsoleSearch;
} = {}) {
	return (
		<AgentConsolePage
			surface="system-ops"
			initialSearch={initialSearch}
			search={search}
			onSearchChange={onSearchChange}
		/>
	);
}
