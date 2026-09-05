import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { BacktestListPage } from "./backtest-list-page";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })}
		>
			{children}
		</QueryClientProvider>
	);
}

const LIVE_RUNS = [
	{
		run_id: "bt-live-002",
		strategy_id: "seed_etf_trend_following",
		strategy_version: "3",
		mode: "backtest",
		status: "running",
		started_at: "2026-08-29T11:00:00Z",
		completed_at: "",
		error_message: "",
		parent_run_id: "",
		benchmark_return: null,
		progress_pct: 64,
		current_step: "walk-forward fold 3",
		completed_days: 128,
		total_days: 200,
	},
	{
		run_id: "bt-live-001",
		strategy_id: "seed_etf_industry_rotation",
		strategy_version: "4",
		mode: "backtest",
		status: "completed",
		started_at: "2026-08-28T09:00:00Z",
		completed_at: "2026-08-28T09:14:00Z",
		error_message: "",
		parent_run_id: "",
		benchmark_return: 7.4,
		progress_pct: 100,
		current_step: "completed",
		completed_days: 244,
		total_days: 244,
	},
];

describe("BacktestListPage", () => {
	it("renders and filters only live governed run summaries", async () => {
		const user = userEvent.setup();
		server.use(http.get("/api/v1/backtests/runs", () => HttpResponse.json({ data: LIVE_RUNS })));

		render(<BacktestListPage />, { wrapper });

		expect(await screen.findByRole("button", { name: "选择回测 bt-live-002" })).toBeInTheDocument();
		expect(screen.getByRole("complementary", { name: "回测运行详情" })).toHaveTextContent("64%");
		expect(screen.getByRole("link", { name: "打开回测结果" })).toHaveAttribute(
			"href",
			"/research/backtests/bt-live-002",
		);

		await user.type(screen.getByRole("searchbox", { name: "搜索回测运行" }), "industry");
		expect(screen.queryByRole("button", { name: "选择回测 bt-live-002" })).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "选择回测 bt-live-001" })).toBeInTheDocument();
		expect(screen.getByRole("complementary", { name: "回测运行详情" })).toHaveTextContent("7.4%");

		await user.click(screen.getByRole("button", { name: "回测对比" }));
		expect(screen.getByRole("dialog", { name: "回测对比" })).toHaveTextContent("bt-live-001");
	});

	it("shows a typed retry error and never falls back to the old static catalog", async () => {
		server.use(
			http.get("/api/v1/backtests/runs", () =>
				HttpResponse.json(
					{ detail: "run catalog unavailable", error_code: "BACKTEST_RUNS_UNAVAILABLE" },
					{ status: 503 },
				),
			),
		);

		render(<BacktestListPage />, { wrapper });

		expect(await screen.findByRole("alert")).toHaveTextContent(/503 BACKTEST_RUNS_UNAVAILABLE/);
		expect(screen.getByRole("button", { name: "重试回测目录" })).toBeInTheDocument();
		expect(screen.queryByText("bt-240427-a")).not.toBeInTheDocument();
	});
});
