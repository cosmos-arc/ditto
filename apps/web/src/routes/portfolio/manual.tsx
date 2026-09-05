import { createFileRoute } from "@tanstack/react-router";
import { PortfolioPage } from "@/features/portfolio";

function ManualPortfolioRoute() {
	return <PortfolioPage mode="manual" />;
}

export const Route = createFileRoute("/portfolio/manual")({
	component: ManualPortfolioRoute,
	staticData: { title: "我的账户 · 手工记录" },
});
