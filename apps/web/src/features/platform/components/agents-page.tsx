import { AgentConsolePage, type AgentConsoleSearch } from "@/features/agent";

export function PlatformAgentsPage({
	initialSearch,
	onSearchChange,
	search,
}: {
	readonly initialSearch?: AgentConsoleSearch;
	readonly onSearchChange?: (search: AgentConsoleSearch) => void;
	readonly search?: AgentConsoleSearch;
} = {}) {
	return <AgentConsolePage initialSearch={initialSearch} search={search} onSearchChange={onSearchChange} />;
}
