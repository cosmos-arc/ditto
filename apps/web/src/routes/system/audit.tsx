import { createFileRoute } from "@tanstack/react-router";
import { SystemPage } from "@/features/system";

export const Route = createFileRoute("/system/audit")({
	component: SystemPage,
	staticData: { title: "System Audit" },
});
