import { createFileRoute } from "@tanstack/react-router";
import { PortfolioPage } from "@/features/portfolio";

function PortfolioOverviewRoute() {
	return <PortfolioPage mode="comparison" />;
}

export const Route = createFileRoute("/portfolio/")({
	component: PortfolioOverviewRoute,
	staticData: { title: "Portfolio Overview" },
});
