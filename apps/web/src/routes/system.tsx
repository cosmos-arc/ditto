import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/system")({
	component: SystemLayout,
	staticData: { title: "System" },
});

function SystemLayout() {
	return <Outlet />;
}
