import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/research/strategies")({
	component: Outlet,
	staticData: { title: "策略" },
});
