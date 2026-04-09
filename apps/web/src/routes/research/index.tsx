import { createFileRoute } from "@tanstack/react-router";
import { ResearchPage } from "@/features/research";

export const Route = createFileRoute("/research/")({
	component: ResearchPage,
	handle: { title: "研究" },
});
