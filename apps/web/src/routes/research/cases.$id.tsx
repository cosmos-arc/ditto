import { createFileRoute } from "@tanstack/react-router";
import { ResearchCaseDetailPage } from "@/features/research";

export const Route = createFileRoute("/research/cases/$id")({
	component: CaseDetailRoute,
	staticData: { title: "研究用例详情" },
});

function CaseDetailRoute() {
	const { id } = Route.useParams();
	return <ResearchCaseDetailPage caseId={decodeURIComponent(id)} />;
}
