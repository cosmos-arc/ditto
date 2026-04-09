import { createFileRoute } from "@tanstack/react-router";
import { RiskPage } from "@/features/trading";

export const Route = createFileRoute("/trading/risk")({
	component: RiskPage,
	handle: { title: "风控中心" },
});
