import { createFileRoute } from "@tanstack/react-router";
import { AiPage } from "@/features/ai/components/ai-page";

export const Route = createFileRoute("/ai/")({
	component: AIOverviewPage,
	handle: { title: "AI Overview" },
});

function AIOverviewPage() {
	return <AiPage />;
}
