import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/trading")({
	component: TradingLayout,
	staticData: { title: "交易" },
});

function TradingLayout() {
	return <Outlet />;
}
