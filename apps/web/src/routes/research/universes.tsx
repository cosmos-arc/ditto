import { createFileRoute } from "@tanstack/react-router";
import { UniverseListPage } from "@/features/research";

export const Route = createFileRoute("/research/universes")({
	component: UniverseListPage,
	staticData: { title: "股票池" },
});
