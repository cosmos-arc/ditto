import { createFileRoute } from "@tanstack/react-router";
import { BacktestPage } from "@/features/backtest";

export const Route = createFileRoute("/research/backtests/$id")({
	component: BacktestPage,
	staticData: { title: "回测结果" },
});
