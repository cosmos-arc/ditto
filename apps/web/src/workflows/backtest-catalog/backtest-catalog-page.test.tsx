import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { BacktestCatalogPage } from "./backtest-catalog-page";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })}
		>
			{children}
		</QueryClientProvider>
	);
}

describe("BacktestCatalogPage", () => {
	beforeEach(() => sessionStorage.clear());
	it.each([false, true])("submits a research run with explicit experimental choice %s", async (experimental) => {
		const user = userEvent.setup();
		let request: unknown;
		server.use(
			http.get("/api/v1/strategies", () =>
				HttpResponse.json({
					data: [
						{
							strategy_id: "seed_etf_trend_swing",
							name: "ETF 趋势追踪",
							version: 1,
							status: "published",
							created_at: "2026-11-08",
							tags: ["etf"],
						},
					],
				}),
			),
			http.post("/api/v1/backtests/runs", async ({ request: incoming }) => {
				request = await incoming.json();
				return HttpResponse.json(
					{ data: { run_id: "new-etf-run", strategy_id: "seed_etf_trend_swing", status: "pending" } },
					{ status: 202 },
				);
			}),
		);
		render(<BacktestCatalogPage />, { wrapper });
		await user.click(screen.getByRole("button", { name: "新建回测" }));
		await screen.findByRole("option", { name: "ETF 趋势追踪 · v1" });
		await user.selectOptions(screen.getByLabelText("策略"), "seed_etf_trend_swing");
		await user.type(screen.getByLabelText("开始日期"), "2026-10-08");
		await user.type(screen.getByLabelText("结束日期"), "2026-11-06");
		const checkbox = screen.getByRole("checkbox", { name: "允许实验数据" });
		expect(checkbox).not.toBeChecked();
		if (experimental) await user.click(checkbox);
		await user.click(screen.getByRole("button", { name: "提交回测" }));
		expect(await screen.findByRole("link", { name: "查看本次回测" })).toHaveAttribute(
			"href",
			"/research/backtests/new-etf-run",
		);
		expect(request).toEqual({
			strategy_id: "seed_etf_trend_swing",
			strategy_version: 1,
			start_date: "2026-10-08",
			end_date: "2026-11-06",
			initial_cash: 1000000,
			allow_experimental_data: experimental,
		});
		expect(screen.getByRole("dialog")).toHaveTextContent("严格历史未认证");
	});
});
