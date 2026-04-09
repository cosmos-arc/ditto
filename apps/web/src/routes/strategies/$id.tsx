import { createFileRoute } from "@tanstack/react-router";
import { StrategyDetailPage } from "@/features/strategy";

export const Route = createFileRoute("/strategies/$id")({
	component: StrategyDetailPage,
	handle: { title: "策略详情" },
});
