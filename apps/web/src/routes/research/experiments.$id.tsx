import { createFileRoute } from "@tanstack/react-router";
import { ExperimentDetailPage } from "@/features/research";

export const Route = createFileRoute("/research/experiments/$id")({
	component: ExperimentDetailRoute,
	staticData: { title: "实验详情" },
});

function ExperimentDetailRoute() {
	const { id } = Route.useParams();
	return <ExperimentDetailPage experimentId={id} />;
}
