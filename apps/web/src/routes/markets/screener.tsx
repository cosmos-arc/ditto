import { createFileRoute } from "@tanstack/react-router";
import { ScreenerPage } from "@/features/screener";

export const Route = createFileRoute("/markets/screener")({
	component: ScreenerPage,
	handle: { title: "市场筛选" },
});
