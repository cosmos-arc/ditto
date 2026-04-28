import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/instruments")({
	component: InstrumentsLayout,
	staticData: { title: "标的详情" },
});

function InstrumentsLayout() {
	return <Outlet />;
}
