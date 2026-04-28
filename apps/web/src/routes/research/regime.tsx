import { createFileRoute } from "@tanstack/react-router";
import { RegimePage } from "@/features/research";

export const Route = createFileRoute("/research/regime")({
	component: RegimePage,
	staticData: { title: "Regime Monitor" },
});
