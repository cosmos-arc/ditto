import { createFileRoute } from "@tanstack/react-router";
import { ResearchCaseDetailWithHandoff } from "@/workflows/strategy-handoff";

export const Route = createFileRoute("/research/cases/$id")({
	component: CaseDetailRoute,
	staticData: { title: "研究用例详情" },
});

function CaseDetailRoute() {
	const { id } = Route.useParams();
	// useParams 已经过一次 URL 解码：再解会把身份中本来就有的 % 序列
	// 二次解码（甚至抛 URIError），用原始 id 原样请求。
	return <ResearchCaseDetailWithHandoff caseId={id} />;
}
