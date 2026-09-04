import { createFileRoute } from "@tanstack/react-router";
import { ReviewDetailPage } from "@/features/research/components/review-detail-page";

interface ReviewDetailSearch {
	readonly strategyId: string;
	readonly version: number;
}

/** 解析 review-detail 所需的策略/版本上下文（queue 链接三参全传）。 */
function parseReviewSearch(search: Record<string, unknown>): ReviewDetailSearch {
	const rawVersion = search.version;
	return {
		strategyId: typeof search.strategyId === "string" ? search.strategyId : "",
		version: typeof rawVersion === "number" ? rawVersion : Number.parseInt(String(rawVersion ?? "0"), 10) || 0,
	};
}

export const Route = createFileRoute("/research/reviews/$id")({
	validateSearch: parseReviewSearch,
	component: ReviewDetailRouteComponent,
	staticData: { title: "审查详情" },
});

function ReviewDetailRouteComponent() {
	const { id: experimentId } = Route.useParams();
	const { strategyId, version } = Route.useSearch();
	if (!strategyId || !version) {
		return (
			<div className="p-6 text-sm text-(--color-foreground-tertiary)">缺少策略/版本上下文（需从审查队列进入）。</div>
		);
	}
	return <ReviewDetailPage experimentId={experimentId} strategyId={strategyId} version={version} />;
}
