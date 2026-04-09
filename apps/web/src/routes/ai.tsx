import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/ai")({
	component: AILayout,
	handle: { title: "AI" },
});

function AILayout() {
	return <Outlet />;
}
