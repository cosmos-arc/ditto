import { createFileRoute } from "@tanstack/react-router";
import { StrategyListPage } from "@/features/strategy";

export const Route = createFileRoute("/research/strategies/")({
	component: StrategyListPage,
	staticData: { title: "策略列表" },
});
