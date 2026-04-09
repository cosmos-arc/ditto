import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/research")({
	component: ResearchLayout,
	handle: { title: "研究" },
});

function ResearchLayout() {
	return <Outlet />;
}
