import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { BacktestCreateForm } from "./backtest-create-form";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("ordinary versioned backtest submission", () => {
	beforeEach(() => sessionStorage.clear());
	it("keeps exact version and business inputs after an unknown response and remount, then restores its receipt", async () => {
		const user = userEvent.setup();
		const requests: { key: string | null; body: unknown }[] = [];
		server.use(
			http.post("/api/v1/backtests/runs", async ({ request }) => {
				requests.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
				if (requests.length === 1) return HttpResponse.error();
				return HttpResponse.json(
					{ data: { run_id: "version-2-run", strategy_id: "seed_etf_industry_rotation", status: "running" } },
					{ status: 202 },
				);
			}),
		);
		const first = render(<BacktestCreateForm strategyId="seed_etf_industry_rotation" version={3} />, { wrapper });
		await screen.findByRole("option", { name: "v2 · deprecated" });
		await user.selectOptions(screen.getByLabelText("策略版本"), "2");
		await user.type(screen.getByLabelText("开始日期"), "2025-01-02");
		await user.type(screen.getByLabelText("结束日期"), "2025-01-31");
		await user.clear(screen.getByLabelText("初始资金（元）"));
		await user.type(screen.getByLabelText("初始资金（元）"), "250000.50");
		await user.click(screen.getByLabelText("允许实验数据"));
		await user.click(screen.getByRole("button", { name: "提交回测" }));
		await screen.findByRole("alert");
		expect(screen.getByLabelText("初始资金（元）")).toHaveValue(250000.5);
		first.unmount();
		const second = render(<BacktestCreateForm strategyId="seed_etf_industry_rotation" version={4} />, { wrapper });
		expect(screen.getByLabelText("策略版本")).toHaveValue("2");
		expect(screen.getByLabelText("开始日期")).toHaveValue("2025-01-02");
		expect(screen.getByLabelText("允许实验数据")).toBeChecked();
		await user.click(screen.getByRole("button", { name: "提交回测" }));
		await screen.findByRole("link", { name: "查看本次回测" });
		expect(requests).toHaveLength(2);
		expect(requests[0]?.key).toBeTruthy();
		expect(requests[1]).toEqual(requests[0]);
		expect(requests[0]?.body).toEqual({
			strategy_id: "seed_etf_industry_rotation",
			strategy_version: 2,
			start_date: "2025-01-02",
			end_date: "2025-01-31",
			initial_cash: 250000.5,
			allow_experimental_data: true,
		});
		second.unmount();
		render(<BacktestCreateForm strategyId="seed_etf_industry_rotation" version={4} />, { wrapper });
		expect(screen.getByRole("link", { name: "查看本次回测" })).toHaveAttribute(
			"href",
			"/research/backtests/version-2-run",
		);
		expect(screen.getByRole("button", { name: "提交回测" })).toBeDisabled();
		expect(requests).toHaveLength(2);
		await user.click(screen.getByRole("button", { name: "开始另一回测" }));
		expect(screen.getByRole("button", { name: "提交回测" })).toBeEnabled();
	});
});
