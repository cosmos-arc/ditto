import { createFileRoute } from "@tanstack/react-router";
import { InstrumentHubPage } from "@/features/instruments";

export const Route = createFileRoute("/instruments/$id")({
	component: InstrumentHubPage,
	staticData: { title: "标的详情" },
});
