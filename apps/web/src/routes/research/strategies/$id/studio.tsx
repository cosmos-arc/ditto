import { createFileRoute } from "@tanstack/react-router";
import { StrategyPage } from "@/features/strategy";

export const Route = createFileRoute("/research/strategies/$id/studio")({
	component: StrategyPage,
	staticData: { title: "Strategy Studio" },
});
