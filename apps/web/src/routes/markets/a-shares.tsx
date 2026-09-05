import { createFileRoute } from "@tanstack/react-router";
import { ASharesPage } from "@/workflows/market-pages";

export const Route = createFileRoute("/markets/a-shares")({
	component: ASharesPage,
	staticData: { title: "A股总览" },
});
