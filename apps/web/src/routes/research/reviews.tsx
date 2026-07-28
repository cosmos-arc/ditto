import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/research/reviews")({
	component: ReviewQueuePage,
	staticData: { title: "审查队列" },
});

function ReviewQueuePage() {
	return <div className="p-6 text-sm text-(--color-foreground-tertiary)">审查队列 · T20 接线中</div>;
}
