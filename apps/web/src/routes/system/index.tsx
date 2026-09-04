import { createFileRoute } from "@tanstack/react-router";
import { SystemPage } from "@/features/system";

export const Route = createFileRoute("/system/")({
	component: SystemPage,
	staticData: { title: "System Ops" },
});
