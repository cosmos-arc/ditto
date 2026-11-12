import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { BacktestListPage } from "../components/backtest-list-page";
import { useBacktestComparison } from "../hooks/use-backtest-comparison";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })}
		>
			{children}
		</QueryClientProvider>
	);
}

function runDto(status: string, progressPct: number, errorMessage = "") {
	return {
		run_id: "bt-live-001",
		strategy_id: "seed_etf_industry_rotation",
		strategy_version: "4",
		mode: "backtest",
		status,
		started_at: "2026-08-28T09:00:00Z",
		completed_at: status === "completed" ? "2026-08-28T09:14:00Z" : "",
		error_message: errorMessage,
		parent_run_id: "",
		benchmark_return: null,
		progress_pct: progressPct,
		current_step: status === "completed" ? "completed" : "day 128/200",
		completed_days: Math.round((progressPct / 100) * 200),
		total_days: 200,
	};
}

describe("useBacktestRuns catalog polling", () => {
	beforeEach(() => {
		sessionStorage.clear();
		useBacktestComparison.setState({ runIds: [], error: null });
	});

	it("keeps reading the real task status of running runs until they settle", async () => {
		// 长任务状态来自真实任务：目录页在存在 pending/running run 时按固定间隔
		// 重新读取，用户离开后回来看到的是当前进度而非提交时快照。
		let served = runDto("running", 64);
		server.use(
			http.get("/api/v1/backtests/runs", () => HttpResponse.json({ data: [served] })),
			http.get("/api/v1/backtests/runs/:runId", ({ params }) =>
				HttpResponse.json({ data: { ...served, run_id: params["runId"] } }),
			),
		);
		render(<BacktestListPage />, { wrapper });
		expect((await screen.findAllByText("64%")).length).toBeGreaterThan(0);

		served = runDto("completed", 100);
		// 不触发任何手动刷新：轮询把真实完成状态带进目录
		await waitFor(() => expect(screen.getAllByText("100%").length).toBeGreaterThan(0), { timeout: 4500 });
		expect(screen.getByRole("complementary", { name: "回测运行详情" })).toHaveTextContent("completed");
	});

	it("stops polling once every run has settled", async () => {
		let fetches = 0;
		server.use(
			http.get("/api/v1/backtests/runs", () => {
				fetches += 1;
				return HttpResponse.json({ data: [runDto("completed", 100)] });
			}),
			http.get("/api/v1/backtests/runs/:runId", ({ params }) =>
				HttpResponse.json({ data: { ...runDto("completed", 100), run_id: params["runId"] } }),
			),
		);
		render(<BacktestListPage />, { wrapper });
		await screen.findAllByText("100%");
		expect(fetches).toBe(1);
	});
});
