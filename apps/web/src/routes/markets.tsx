import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/markets")({
	component: MarketsLayout,
	handle: { title: "市场" },
});

function MarketsLayout() {
	return <Outlet />;
}
