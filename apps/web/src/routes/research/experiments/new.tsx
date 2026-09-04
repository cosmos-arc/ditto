import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ExperimentCreatePage } from "@/features/research";

function NewExperimentRoute() {
	const navigate = useNavigate();
	return (
		<ExperimentCreatePage
			onLaunched={(experimentId) => void navigate({ to: "/research/experiments/$id", params: { id: experimentId } })}
		/>
	);
}

export const Route = createFileRoute("/research/experiments/new")({
	component: NewExperimentRoute,
	staticData: { title: "创建实验" },
});
