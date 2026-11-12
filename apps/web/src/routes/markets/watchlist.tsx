import { createFileRoute } from "@tanstack/react-router";
import { WatchlistPage } from "@/workflows/market-pages";

/** 解析 票 748 研究判断来源（判断「转入次日计划」链接携带）。 */
function parseWatchlistSearch(search: Record<string, unknown>): { judgment: string } {
	return {
		judgment: typeof search["judgment"] === "string" ? search["judgment"] : "",
	};
}

export const Route = createFileRoute("/markets/watchlist")({
	validateSearch: parseWatchlistSearch,
	component: WatchlistRouteComponent,
	staticData: { title: "自选监控" },
});

function WatchlistRouteComponent() {
	const { judgment } = Route.useSearch();
	return <WatchlistPage sourceJudgmentId={judgment} />;
}
