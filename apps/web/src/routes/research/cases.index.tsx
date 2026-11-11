import { createFileRoute } from "@tanstack/react-router";
import { ResearchCaseListPage } from "@/features/research";

export const Route = createFileRoute("/research/cases/")({
	component: ResearchCaseListPage,
	staticData: { title: "研究用例" },
});
