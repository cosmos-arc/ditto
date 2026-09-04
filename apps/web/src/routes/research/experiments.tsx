import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/research/experiments")({
	component: Outlet,
	staticData: { title: "实验" },
});
