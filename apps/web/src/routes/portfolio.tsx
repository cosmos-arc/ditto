import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/portfolio")({
	component: PortfolioLayout,
	staticData: { title: "Portfolio" },
});

function PortfolioLayout() {
	return <Outlet />;
}
