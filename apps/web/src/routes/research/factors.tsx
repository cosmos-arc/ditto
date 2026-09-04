import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/research/factors")({
	component: Outlet,
	staticData: { title: "因子研究" },
});
