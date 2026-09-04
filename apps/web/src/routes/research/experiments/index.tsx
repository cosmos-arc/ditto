import { createFileRoute } from "@tanstack/react-router";
import { ExperimentListPage } from "@/features/research";

export const Route = createFileRoute("/research/experiments/")({
	component: ExperimentListPage,
	staticData: { title: "实验队列" },
});
