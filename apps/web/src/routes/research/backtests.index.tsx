import { createFileRoute } from "@tanstack/react-router";
import { BacktestCatalogPage } from "@/workflows/backtest-catalog";

export const Route = createFileRoute("/research/backtests/")({
	component: BacktestCatalogPage,
	staticData: { title: "回测列表" },
});
