import { createFileRoute } from "@tanstack/react-router";
import { HomePage } from "@/features/home";

export const Route = createFileRoute("/")({
	component: HomePage,
	handle: { title: "首页" },
});
