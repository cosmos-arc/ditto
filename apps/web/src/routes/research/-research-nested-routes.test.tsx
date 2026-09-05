import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { mockExperimentDetail } from "@/mocks/fixtures/experiment-workbench";
import { mockReviewPacket } from "@/mocks/fixtures/review-live";
import { server } from "@/mocks/server";
import { QueryProvider } from "@/providers";
import { routeTree } from "@/routeTree.gen";

function renderRoute(path: string): void {
	const history = createMemoryHistory({ initialEntries: [path] });
	const router = createRouter({ routeTree, history });

	render(
		<QueryProvider>
			<RouterProvider router={router} />
		</QueryProvider>,
	);
}

describe("research nested routes", () => {
	beforeEach(() => {
		server.use(
			http.get("/api/v1/research/experiments/exp-r3", () =>
				HttpResponse.json({
					data: { ...mockExperimentDetail, experiment_id: "exp-r3" },
				}),
			),
			http.get("/api/v1/research/experiments/exp-r3/review-packet", () =>
				HttpResponse.json({
					data: { ...mockReviewPacket, experiment_id: "exp-r3" },
				}),
			),
		);
	});

	it("renders the strategy studio instead of the strategy list", async () => {
		renderRoute("/research/strategies/seed_stock_selection_rotation/studio");

		expect(await screen.findByRole("tablist", { name: "编辑模式" })).toBeInTheDocument();
		expect(screen.queryByRole("tab", { name: "概览" })).not.toBeInTheDocument();
		expect(screen.queryByText("Strategies")).not.toBeInTheDocument();
	});

	it("gives the factor catalog its frozen catalog workspace without a duplicate research bar", async () => {
		renderRoute("/research/factors");

		expect(await screen.findByRole("region", { name: "受控因子目录" })).toBeInTheDocument();
		expect(screen.queryByRole("navigation", { name: "研究子导航" })).not.toBeInTheDocument();
	});

	it("gives the strategy catalog its immersive governed workspace", async () => {
		renderRoute("/research/strategies");

		expect(await screen.findByRole("table", { name: "策略目录" })).toBeInTheDocument();
		expect(screen.queryByRole("navigation", { name: "研究子导航" })).not.toBeInTheDocument();
	});

	it("gives the universe catalog its immersive governed workspace", async () => {
		renderRoute("/research/universes");

		expect(await screen.findByRole("region", { name: "受控股票池目录" })).toBeInTheDocument();
		expect(screen.queryByRole("navigation", { name: "研究子导航" })).not.toBeInTheDocument();
	});

	it("gives experiment planning the full governed Studio workspace", async () => {
		renderRoute("/research/experiments/new");

		expect(await screen.findByRole("region", { name: "实验规划工作区" })).toBeInTheDocument();
		expect(screen.queryByRole("navigation", { name: "研究子导航" })).not.toBeInTheDocument();
	});

	it("renders the factor analysis child instead of leaving the factor catalog mounted", async () => {
		renderRoute("/research/factors/momentum_1m");

		expect(await screen.findByText("诊断范围未绑定")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "诊断详情" })).toBeDisabled();
		expect(screen.queryByRole("region", { name: "受控因子目录" })).not.toBeInTheDocument();
	});

	it("renders the experiment detail instead of the experiment list", async () => {
		renderRoute("/research/experiments/exp-r3");

		expect(await screen.findByRole("heading", { name: "Experiment exp-r3" })).toBeInTheDocument();
		expect(screen.getByText(/completed · finalized · revision 9/)).toBeInTheDocument();
		expect(screen.queryByText("Experiments")).not.toBeInTheDocument();
		expect(screen.queryByRole("navigation", { name: "研究子导航" })).not.toBeInTheDocument();
	});

	it("renders the review detail instead of the review queue", async () => {
		renderRoute("/research/reviews/exp-r3?strategyId=seed_stock_selection_rotation&version=2");

		expect((await screen.findAllByText("experiment exp-r3")).length).toBeGreaterThan(0);
		expect(screen.queryByText("Reviews")).not.toBeInTheDocument();
		expect(screen.queryByRole("navigation", { name: "研究子导航" })).not.toBeInTheDocument();
	});

	it("renders the backtest result instead of leaving the backtest catalog mounted", async () => {
		renderRoute("/research/backtests/bt-001");

		expect(await screen.findByRole("heading", { name: "Backtest bt-001" })).toBeInTheDocument();
		expect(screen.queryByRole("region", { name: "受控回测目录" })).not.toBeInTheDocument();
		expect(screen.queryByRole("navigation", { name: "研究子导航" })).not.toBeInTheDocument();
	});
});
