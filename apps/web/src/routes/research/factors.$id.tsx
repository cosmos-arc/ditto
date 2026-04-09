import { createFileRoute } from "@tanstack/react-router";
import { FactorPage } from "@/features/research";

export const Route = createFileRoute("/research/factors/$id")({
	component: FactorPage,
	handle: { title: "因子分析" },
});
