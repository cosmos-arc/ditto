import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/markets")({
	component: MarketsLayout,
	staticData: { title: "市场" },
});

function MarketsLayout() {
	return <Outlet />;
}
