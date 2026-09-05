import { createFileRoute } from "@tanstack/react-router";
import { PortfolioRiskWithDecisionBriefing } from "@/workflows/portfolio-decision";

export const Route = createFileRoute("/portfolio/risk")({
	component: PortfolioRiskWithDecisionBriefing,
	staticData: { title: "风控中心" },
});
