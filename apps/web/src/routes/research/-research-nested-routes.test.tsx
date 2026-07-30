import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
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

	it("renders the experiment detail instead of the experiment list", async () => {
		renderRoute("/research/experiments/exp-r3");

		expect(await screen.findByText("实验详情 · T19 接线中")).toBeInTheDocument();
		expect(screen.queryByText("Experiments")).not.toBeInTheDocument();
	});

	it("renders the review detail instead of the review queue", async () => {
		renderRoute("/research/reviews/exp-r3?strategyId=seed_stock_selection_rotation&version=2");

		expect(await screen.findByText("experiment exp-r3")).toBeInTheDocument();
		expect(screen.queryByText("Reviews")).not.toBeInTheDocument();
	});
});
