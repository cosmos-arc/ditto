import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/research/experiments/$id")({
	component: ExperimentDetailPage,
	staticData: { title: "实验详情" },
});

function ExperimentDetailPage() {
	return <div className="p-6 text-sm text-(--color-foreground-tertiary)">实验详情 · T19 接线中</div>;
}
