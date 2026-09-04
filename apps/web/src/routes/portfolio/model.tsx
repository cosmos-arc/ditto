import { createFileRoute } from "@tanstack/react-router";
import { PortfolioPage } from "@/features/portfolio";

function ModelPortfolioRoute() {
	return <PortfolioPage mode="model" />;
}

export const Route = createFileRoute("/portfolio/model")({
	component: ModelPortfolioRoute,
	staticData: { title: "Model Portfolio" },
});
