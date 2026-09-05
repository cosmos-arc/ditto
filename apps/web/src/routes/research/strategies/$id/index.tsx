import { createFileRoute } from "@tanstack/react-router";
import { StrategyGovernanceDetailPage } from "@/workflows/strategy-governance";

export const Route = createFileRoute("/research/strategies/$id/")({
	component: StrategyGovernanceDetailPage,
	staticData: { title: "策略详情" },
});
