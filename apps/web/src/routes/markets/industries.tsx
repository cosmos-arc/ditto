import { createFileRoute } from "@tanstack/react-router";
import { IndustryRotationPage } from "@/features/selection";

export const Route = createFileRoute("/markets/industries")({
	component: IndustryRotationPage,
	staticData: { title: "行业轮动" },
});
