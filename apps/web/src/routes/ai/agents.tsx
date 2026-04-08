import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/ai/agents")({
	component: AgentsPage,
	handle: { title: "Agent Console" },
});

function AgentsPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			Agent Console — 占位
		</div>
	);
}
