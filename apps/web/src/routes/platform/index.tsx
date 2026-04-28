import { createFileRoute } from "@tanstack/react-router";
import { PlatformPage } from "@/features/platform";

export const Route = createFileRoute("/platform/")({
	component: PlatformPage,
	staticData: { title: "平台管理" },
});
