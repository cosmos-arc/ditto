import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { researchHandlers } from "@/mocks/handlers/research";
import { server } from "@/mocks/server";

// jsdom 无法承载 fancy-canvas：barrel 级 stub，捕获 props 断言双轴与序列。
const cockpitProps: Array<Record<string, unknown>> = [];
vi.mock("@/components/chart", () => ({
	ChartCockpit: (props: Record<string, unknown>) => {
		cockpitProps.push(props);
		return createElement("div", {
			"data-testid": "cockpit-stub",
			"data-chart-panes": "1",
		});
	},
}));

import { FactorSeriesCharts } from "./factor-series-charts";

function createWrapper() {
	const client = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return createElement(QueryClientProvider, { client }, children);
	};
}

beforeEach(() => {
	server.use(...researchHandlers);
	cockpitProps.length = 0;
});

describe("FactorSeriesCharts", () => {
	it("renders IC/IR dual-axis and quantile/LS charts plus the monthly heatmap", async () => {
		render(<FactorSeriesCharts endDate="2026-03-31" factorId="momentum_20" startDate="2026-01-05" />, {
			wrapper: createWrapper(),
		});
		expect(await screen.findByTestId("factor-ic-chart-momentum_20")).toBeInTheDocument();
		expect(screen.getByTestId("factor-quantile-chart-momentum_20")).toBeInTheDocument();

		// 双轴：IC 左轴、滚动 IR 右轴
		const icChart = cockpitProps[0] as { series: Array<{ id: string; priceScaleId?: string }> };
		expect(icChart.series.map((spec) => [spec.id, spec.priceScaleId])).toEqual([
			["ic", "left"],
			["rolling_ir", "right"],
		]);
		// 分位 + 多空
		const quantileChart = cockpitProps[1] as { series: Array<{ id: string }> };
		expect(quantileChart.series.map((spec) => spec.id)).toEqual(["q_1", "q_2", "q_3", "q_4", "q_5", "ls_spread"]);

		// 热力图：mock 两个月份单元格 + 缺月占位
		const heatmap = screen.getByTestId("factor-monthly-ic-momentum_20");
		expect(heatmap.textContent).toContain("0.051");
		expect(heatmap.textContent).toContain("-0.023");
		expect(heatmap.textContent).toContain("—");
	});

	it("degrades to the explicit research-gated state when the endpoint rejects", async () => {
		// msw 后注册的 handler 优先匹配：blocked_factor 命中 422，其余走通用 handler。
		server.use(...researchHandlers);
		server.use(
			http.get("/api/v1/research/factors/blocked_factor/evaluation-series", () =>
				HttpResponse.json(
					{
						detail: "forward_return_service.compute() not available in production",
						error_code: "APP_QUERY_ERROR",
					},
					{ status: 422 },
				),
			),
		);
		render(<FactorSeriesCharts endDate="2026-03-31" factorId="blocked_factor" startDate="2026-01-05" />, {
			wrapper: createWrapper(),
		});
		expect(await screen.findByText(/评估序列为研究语义/, {}, { timeout: 3000 })).toBeInTheDocument();
		expect(screen.getByRole("alert")).toBeInTheDocument();
	});
});
