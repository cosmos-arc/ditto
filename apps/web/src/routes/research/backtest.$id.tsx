import { createFileRoute } from "@tanstack/react-router";
import { BacktestPage } from "@/features/backtest";

export const Route = createFileRoute("/research/backtest/$id")({
	component: BacktestPage,
	staticData: { title: "回测结果" },
});
