import { createFileRoute } from "@tanstack/react-router";
import { StrategyDetailPage } from "@/features/strategy";

export const Route = createFileRoute("/research/strategies/$id")({
	component: StrategyDetailPage,
	staticData: { title: "策略详情" },
});
