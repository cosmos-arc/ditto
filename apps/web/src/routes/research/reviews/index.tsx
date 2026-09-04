import { createFileRoute } from "@tanstack/react-router";
import { ReviewQueuePage } from "@/features/research/components/review-queue-page";

export const Route = createFileRoute("/research/reviews/")({
	component: ReviewQueuePage,
	staticData: { title: "审查队列" },
});
