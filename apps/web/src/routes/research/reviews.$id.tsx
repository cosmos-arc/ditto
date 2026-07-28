import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/research/reviews/$id")({
	component: ReviewDetailPage,
	staticData: { title: "审查详情" },
});

function ReviewDetailPage() {
	return <div className="p-6 text-sm text-(--color-foreground-tertiary)">审查详情 · T20 接线中</div>;
}
