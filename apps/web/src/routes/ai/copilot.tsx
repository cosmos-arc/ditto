import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/ai/copilot")({
	component: CopilotPage,
	handle: { title: "AI Copilot" },
});

function CopilotPage() {
	return (
		<div className="flex h-full items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			AI Copilot — 占位
		</div>
	);
}
