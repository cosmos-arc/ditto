import { createFileRoute } from "@tanstack/react-router";
import { PlatformAgentsPage } from "@/features/platform";

export const Route = createFileRoute("/platform/agents")({
	component: PlatformAgentsPage,
	staticData: { title: "Agent Console" },
});
