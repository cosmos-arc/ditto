import { createFileRoute } from "@tanstack/react-router";
import { StrategyPage } from "@/features/strategy";

export const Route = createFileRoute("/research/strategy-studio")({
	component: StrategyPage,
	handle: { title: "Strategy Studio" },
});
