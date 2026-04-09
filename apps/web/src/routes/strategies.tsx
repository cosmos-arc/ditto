import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/strategies")({
	component: StrategiesLayout,
	handle: { title: "策略详情" },
});

function StrategiesLayout() {
	return <Outlet />;
}
