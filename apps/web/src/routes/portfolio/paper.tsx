import { createFileRoute } from "@tanstack/react-router";
import { PortfolioPage } from "@/features/portfolio";

function PaperPortfolioRoute() {
	return <PortfolioPage mode="paper" />;
}

export const Route = createFileRoute("/portfolio/paper")({
	component: PaperPortfolioRoute,
	staticData: { title: "Paper Account" },
});
