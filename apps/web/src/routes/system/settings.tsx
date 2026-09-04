import { createFileRoute } from "@tanstack/react-router";
import { SystemSettingsPage } from "@/features/system";

export const Route = createFileRoute("/system/settings")({
	component: SystemSettingsPage,
	staticData: { title: "System Settings" },
});
