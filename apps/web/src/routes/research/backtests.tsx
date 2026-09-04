import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/research/backtests")({
	component: Outlet,
	staticData: { title: "回测" },
});
