import { createFileRoute } from "@tanstack/react-router";
import { MarketsPage } from "@/features/markets";

export const Route = createFileRoute("/markets/")({
	component: MarketsPage,
	staticData: { title: "跨市场总览" },
});
