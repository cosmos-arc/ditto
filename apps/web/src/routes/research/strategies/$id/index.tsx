import { createFileRoute } from "@tanstack/react-router";
import { StrategyGovernanceDetailPage } from "@/workflows/strategy-governance";

/** 解析 票 748 研究判断的回程上下文（进入验证链接携带；直接进入时缺省）。 */
function parseStrategyDetailSearch(search: Record<string, unknown>): {
	fromJudgment?: string;
} {
	const raw = search["fromJudgment"];
	return typeof raw === "string" && raw.trim() ? { fromJudgment: raw } : {};
}

export const Route = createFileRoute("/research/strategies/$id/")({
	validateSearch: parseStrategyDetailSearch,
	component: StrategyDetailRouteComponent,
	staticData: { title: "策略详情" },
});

function StrategyDetailRouteComponent() {
	const { fromJudgment } = Route.useSearch();
	return <StrategyGovernanceDetailPage fromJudgment={fromJudgment ?? ""} />;
}
