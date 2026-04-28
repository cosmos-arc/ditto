import { createFileRoute } from "@tanstack/react-router";
import { PlatformSettingsPage } from "@/features/platform";

export const Route = createFileRoute("/platform/settings")({
	component: PlatformSettingsPage,
	staticData: { title: "平台设置" },
});
