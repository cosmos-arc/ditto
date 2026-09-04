import { createFileRoute } from "@tanstack/react-router";
import { FactorListPage } from "@/features/research";

export const Route = createFileRoute("/research/factors/")({
	component: FactorListPage,
	staticData: { title: "因子列表" },
});
