import { BacktestListPage } from "@/features/backtest";
import { BacktestCreateForm } from "./backtest-create-form";

export function BacktestCatalogPage() {
	return <BacktestListPage createForm={<BacktestCreateForm />} />;
}
