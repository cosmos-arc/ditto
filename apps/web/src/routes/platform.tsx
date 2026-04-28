import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/platform")({
	component: PlatformLayout,
	staticData: { title: "平台管理" },
});

function PlatformLayout() {
	return <Outlet />;
}
