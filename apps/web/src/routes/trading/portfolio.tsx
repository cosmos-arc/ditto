import { createFileRoute } from "@tanstack/react-router";
import { PortfolioPage } from "@/features/trading";

export const Route = createFileRoute("/trading/portfolio")({
	component: PortfolioPage,
	staticData: { title: "组合总览" },
});
