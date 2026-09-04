import { createFileRoute } from "@tanstack/react-router";
import { RiskPage } from "@/features/portfolio";

export const Route = createFileRoute("/portfolio/risk")({
	component: RiskPage,
	staticData: { title: "风控中心" },
});
