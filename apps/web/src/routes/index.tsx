import { createFileRoute } from "@tanstack/react-router";
import { HomePage } from "@/workflows/home-dashboard";

export const Route = createFileRoute("/")({
	component: HomePage,
	staticData: { title: "首页" },
});
