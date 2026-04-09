import { createFileRoute } from "@tanstack/react-router";
import { IntelligencePage } from "@/features/markets";

export const Route = createFileRoute("/markets/intelligence")({
	component: IntelligencePage,
	handle: { title: "市场情报" },
});
