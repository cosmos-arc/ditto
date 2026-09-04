import { createFileRoute } from "@tanstack/react-router";
import { ResearchPage } from "@/features/research";

export const Route = createFileRoute("/research/")({
	component: ResearchPage,
	staticData: { title: "研究工作区" },
});
