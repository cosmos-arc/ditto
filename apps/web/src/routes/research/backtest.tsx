import { createFileRoute } from "@tanstack/react-router";
import { BacktestListPage } from "@/features/backtest";

export const Route = createFileRoute("/research/backtest")({
	component: BacktestListPage,
	staticData: { title: "回测列表" },
});
