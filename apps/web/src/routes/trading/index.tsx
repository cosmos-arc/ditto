import { createFileRoute } from "@tanstack/react-router";
import { TradingPage } from "@/features/trading";

export const Route = createFileRoute("/trading/")({
	component: TradingPage,
	staticData: { title: "交易总览" },
});
