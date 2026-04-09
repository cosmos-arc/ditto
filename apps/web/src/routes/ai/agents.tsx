import { createFileRoute } from "@tanstack/react-router";
import { AgentsPage } from "@/features/ai/components/agents-page";

export const Route = createFileRoute("/ai/agents")({
	component: AgentsPageRoute,
	handle: { title: "Agent Console" },
});

function AgentsPageRoute() {
	return <AgentsPage />;
}
