import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { FillLedgerList } from "./fill-ledger-list";
import { PositionsSummary } from "./positions-summary";
import { SignalToOrderPipelineStrip } from "./signal-to-order-pipeline-strip";
import { SignalsList } from "./signals-list";
import { TradingOverviewOrdersPanel } from "./trading-overview-orders-panel";
import { TradingOverviewSignalsPanel } from "./trading-overview-signals-panel";

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});

	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "false");
});

describe("R1 trading live responsive states", () => {
	it("announces the fill ledger loading state", () => {
		server.use(
			http.get("/api/v1/trade/fills", async () => {
				await delay("infinite");
				return HttpResponse.error();
			}),
		);

		render(<FillLedgerList />, { wrapper: createWrapper() });

		expect(screen.getByRole("status", { name: "手工执行流水加载中" })).toBeInTheDocument();
	});

	it("announces the signal queue loading state", () => {
		server.use(
			http.get("/api/v1/trade/daily-decision/v2", async () => {
				await delay("infinite");
				return HttpResponse.error();
			}),
		);

		render(<TradingOverviewSignalsPanel />, { wrapper: createWrapper() });

		expect(screen.getByRole("status", { name: "信号队列加载中" })).toBeInTheDocument();
	});

	it("announces the order panel loading state", () => {
		server.use(
			http.get("/api/v1/trade/daily-decision/v2", async () => {
				await delay("infinite");
				return HttpResponse.error();
			}),
		);

		render(<TradingOverviewOrdersPanel />, { wrapper: createWrapper() });

		expect(screen.getByRole("status", { name: "委托订单加载中" })).toBeInTheDocument();
	});

	it("reflows live signal rows on narrow screens", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });

		const row = await screen.findByRole("button", { name: /#510300/ });
		expect(row).toHaveClass("flex-col");
		expect(row).toHaveClass("sm:flex-row");
		expect(row).toHaveClass("items-start");
	});

	it("announces the pipeline loading state", () => {
		server.use(
			http.get("/api/v1/trade/daily-decision/v2", async () => {
				await delay("infinite");
				return HttpResponse.error();
			}),
		);

		render(<SignalToOrderPipelineStrip />, { wrapper: createWrapper() });

		expect(screen.getByRole("status", { name: "Pipeline 加载中" })).toBeInTheDocument();
	});

	it("reflows fill rows on narrow screens without clipping financial fields", async () => {
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const list = await screen.findByRole("list", { name: "手工成交记录" });
		const [row] = await screen.findAllByRole("listitem");
		expect(screen.getByRole("status", { name: "手工执行流水加载完成" })).toHaveTextContent("共 1 笔");
		expect(list).toHaveAttribute("tabindex", "0");
		expect(list).toHaveClass("overflow-x-auto");
		expect(row).toHaveClass("grid-cols-2");
		expect(row.className).toContain("sm:grid-cols-[");
		expect(within(row).getByText("数量")).toHaveClass("sm:hidden");
		expect(within(row).getByText("成交价")).toHaveClass("sm:hidden");
		expect(within(row).getByText("费用")).toHaveClass("sm:hidden");
	});

	it("announces an empty fill ledger as a completed status", async () => {
		server.use(
			http.get("/api/v1/trade/fills", () =>
				HttpResponse.json({
					data: [],
					pagination: { total: 0, limit: 0, offset: 0, has_more: false },
				}),
			),
			http.get("/api/v1/trade/fills/effective", () => HttpResponse.json({ data: [] })),
			http.get("/api/v1/trade/fill-adjustments", () => HttpResponse.json({ data: [] })),
		);

		render(<FillLedgerList />, { wrapper: createWrapper() });

		const status = await screen.findByRole("status", { name: "手工执行流水状态" });
		expect(status).toHaveTextContent("尚未录入手工成交");
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});

	it("keeps signal loading, error, and empty states distinct and retries errors", async () => {
		server.use(
			http.get(
				"/api/v1/trade/daily-decision/v2",
				() => HttpResponse.json({ detail: "temporary failure" }, { status: 503 }),
				{ once: true },
			),
		);
		const user = userEvent.setup();

		render(<TradingOverviewSignalsPanel />, { wrapper: createWrapper() });

		const alert = await screen.findByRole("alert");
		expect(alert).toHaveTextContent("信号队列加载失败");
		expect(screen.queryByText("暂无待复核信号")).not.toBeInTheDocument();

		await user.click(within(alert).getByRole("button", { name: "重试" }));

		await expect(screen.findByText("#510300")).resolves.toBeInTheDocument();
		expect(screen.getByRole("status", { name: "信号队列加载完成" })).toHaveTextContent("共 1 条");
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});

	it("shows a retryable live positions error instead of a blank panel", async () => {
		server.use(
			http.get(
				"/api/v1/trade/daily-decision/v2",
				() => HttpResponse.json({ detail: "temporary failure" }, { status: 503 }),
				{ once: true },
			),
		);
		const user = userEvent.setup();

		render(<PositionsSummary />, { wrapper: createWrapper() });

		const alert = await screen.findByRole("alert");
		expect(alert).toHaveTextContent("持仓汇总加载失败");

		await user.click(within(alert).getByRole("button", { name: "重试" }));

		await expect(screen.findAllByText("#510300")).resolves.not.toHaveLength(0);
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});

	it("keeps order errors separate from empty results and retries both live sources", async () => {
		server.use(
			http.get(
				"/api/v1/trade/daily-decision/v2",
				() => HttpResponse.json({ detail: "temporary failure" }, { status: 503 }),
				{ once: true },
			),
		);
		const user = userEvent.setup();

		render(<TradingOverviewOrdersPanel />, { wrapper: createWrapper() });

		const alert = await screen.findByRole("alert");
		expect(alert).toHaveTextContent("委托订单加载失败");
		expect(screen.queryByText("尚未录入手工成交")).not.toBeInTheDocument();

		await user.click(within(alert).getByRole("button", { name: "重试" }));

		await expect(screen.findByText("fill-159915-001")).resolves.toBeInTheDocument();
		expect(screen.getByRole("status", { name: "委托订单加载完成" })).toHaveTextContent("成交 1 笔");
		expect(screen.queryByRole("alert")).not.toBeInTheDocument();
	});

	it("prioritizes an order error while the other live source is still pending", async () => {
		server.use(
			http.get("/api/v1/trade/daily-decision/v2", () =>
				HttpResponse.json({ detail: "temporary failure" }, { status: 503 }),
			),
			http.get("/api/v1/trade/fills", async () => {
				await delay("infinite");
				return HttpResponse.error();
			}),
		);

		render(<TradingOverviewOrdersPanel />, { wrapper: createWrapper() });

		await expect(screen.findByRole("alert")).resolves.toHaveTextContent("委托订单加载失败");
		expect(screen.queryByRole("status", { name: "委托订单加载中" })).not.toBeInTheDocument();
	});

	it("stacks the pipeline summary on mobile and recovers from a failed source", async () => {
		server.use(
			http.get("/api/v1/trade/fills", () => HttpResponse.json({ detail: "temporary failure" }, { status: 503 }), {
				once: true,
			}),
		);
		const user = userEvent.setup();

		render(<SignalToOrderPipelineStrip />, { wrapper: createWrapper() });

		const alert = await screen.findByRole("alert");
		expect(alert).toHaveTextContent("信号到订单流水线加载失败");

		await user.click(within(alert).getByRole("button", { name: "重试" }));

		const stages = await screen.findByRole("status", { name: "Pipeline 数据" });
		expect(stages).toHaveClass("grid-cols-1");
		expect(stages).toHaveClass("sm:grid-cols-4");
		expect(within(stages).getByText("信号池")).toBeInTheDocument();
	});

	it("prioritizes a pipeline error while another source is still pending", async () => {
		server.use(
			http.get("/api/v1/trade/daily-decision/v2", async () => {
				await delay("infinite");
				return HttpResponse.error();
			}),
			http.get("/api/v1/trade/fills", () => HttpResponse.json({ detail: "temporary failure" }, { status: 503 })),
		);

		render(<SignalToOrderPipelineStrip />, { wrapper: createWrapper() });

		await expect(screen.findByRole("alert")).resolves.toHaveTextContent("信号到订单流水线加载失败");
		expect(screen.queryByRole("status", { name: "Pipeline 加载中" })).not.toBeInTheDocument();
	});
});
