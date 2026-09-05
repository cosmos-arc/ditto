import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/research/reviews")({
	component: Outlet,
	staticData: { title: "审查" },
});
