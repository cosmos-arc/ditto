import { createFileRoute } from "@tanstack/react-router";
import { WatchlistPage } from "@/features/markets";

export const Route = createFileRoute("/markets/watchlist")({
	component: WatchlistPage,
	staticData: { title: "自选监控" },
});
