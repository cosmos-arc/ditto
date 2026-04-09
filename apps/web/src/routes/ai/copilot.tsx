import { createFileRoute } from "@tanstack/react-router";
import { CopilotPage } from "@/features/ai/components/copilot-page";

export const Route = createFileRoute("/ai/copilot")({
	component: CopilotPageRoute,
	handle: { title: "AI Copilot" },
});

function CopilotPageRoute() {
	return <CopilotPage />;
}
