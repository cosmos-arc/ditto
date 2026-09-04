import { createFileRoute } from "@tanstack/react-router";
import { SignalsPage } from "@/features/portfolio";

export const Route = createFileRoute("/portfolio/review")({
	component: SignalsPage,
	staticData: { title: "Portfolio Review" },
});
