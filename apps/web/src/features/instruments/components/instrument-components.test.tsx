import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { instrumentsHandlers } from "@/mocks/handlers/instruments";
import { server } from "@/mocks/server";
import { InstrumentChartView } from "./instrument-chart-view";
import { InstrumentHubPage } from "./instrument-hub-page";
import { InstrumentMetaStrip } from "./instrument-meta-strip";
import { InstrumentOverview } from "./instrument-overview";
import { InstrumentPageOverlays } from "./instrument-page-overlays";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return { ...actual, useParams: () => ({ id: "1000001" }) };
});
vi.mock("@/components/chart", () => ({
	ChartCockpit: (props: unknown) => {
		cockpitProps.push(props);
		return createElement("div", {
			"data-testid": "cockpit-stub",
			"data-chart-aria": (props as { ariaLabel: string }).ariaLabel,
		});
	},
}));

// lightweight-charts / fancy-canvas 在 jsdom 中产生大量未处理错误；图表内部
// 行为由 cockpit 组件测试覆盖，这里在 barrel 层同步 mock 组件（视图的重采样
// 从 chart-data 叶模块导入，保持真实实现），只断言本视图喂养的外部合同。
const cockpitProps: unknown[] = [];

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	localStorage.clear();
	cockpitProps.length = 0;
	server.use(...instrumentsHandlers);
});

describe("InstrumentMetaStrip", () => {
	it("渲染标的信息", async () => {
		render(<InstrumentMetaStrip id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText("600519 · SSE")).resolves.toBeInTheDocument();
	});

	it("只显示公开 metadata 合同提供的身份字段", async () => {
		render(<InstrumentMetaStrip id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("交易中")).resolves.toBeInTheDocument();
		await expect(screen.findByText("2001-08-27")).resolves.toBeInTheDocument();
		expect(screen.queryByText("白酒")).not.toBeInTheDocument();
	});
});

describe("InstrumentOverview", () => {
	it("渲染可追溯的标的档案", async () => {
		render(<InstrumentOverview id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("标的档案")).resolves.toBeInTheDocument();
		await expect(screen.findByText("1000001")).resolves.toBeInTheDocument();
	});

	it("明确基本面未默认加载的原因", async () => {
		render(<InstrumentOverview id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/实验数据默认关闭/)).resolves.toBeInTheDocument();
	});
});

describe("InstrumentChartView", () => {
	it("渲染行情图表区域与工具栏", async () => {
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("行情图表")).resolves.toBeInTheDocument();
		expect(screen.getByTestId("chart-周期-control")).toBeInTheDocument();
		expect(screen.getByTestId("chart-复权-control")).toBeInTheDocument();
		expect(screen.getByTestId("chart-experimental-toggle")).toBeInTheDocument();
	});

	it("以蜡烛形态喂给图表 shell 并展示 Primary Answer 关键数字", async () => {
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await screen.findByTestId("cockpit-stub");
		const props = cockpitProps.at(-1) as {
			series: Array<{
				id: string;
				kind: string;
				bars: Array<{ open: number; high: number; low: number; close: number; volume: number }>;
			}>;
		};
		expect(props.series[0]!.id).toBe("ohlc");
		expect(props.series[0]!.kind).toBe("candle");
		// mock 两根日 K（03-09/03-10），OHLCV 完整进入 view model
		expect(props.series[0]!.bars).toHaveLength(2);
		expect(props.series[0]!.bars[1]).toMatchObject({ open: 1744.6, close: 1750.2, volume: 3210000 });

		const scope = await screen.findByText(/2026-03-10 收盘/);
		expect(scope.closest("[data-primary-answer]")).not.toBeNull();
		expect(screen.getByText("1750.20")).toBeInTheDocument();
		expect(screen.getByText(/\+3\.90/)).toBeInTheDocument();
		expect(screen.getByText(/1732\.10–1768\.80/)).toBeInTheDocument();
		expect(screen.getByText(/快照标识未由接口提供/)).toBeInTheDocument();
	});

	it("周线切换把日 K 聚合为周桶", async () => {
		const user = userEvent.setup();
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await screen.findByTestId("cockpit-stub");
		await user.click(screen.getByRole("button", { name: "周" }));
		const props = cockpitProps.at(-1) as { series: Array<{ bars: unknown[] }> };
		expect(props.series[0]!.bars).toHaveLength(1);
	});

	it("复权切换触发重新取数（查询键携带 adjustment）", async () => {
		const user = userEvent.setup();
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await screen.findByTestId("cockpit-stub");
		await user.click(screen.getByRole("button", { name: "前复权" }));
		await screen.findByText(/复权：qfq · experimental：关/);
	});

	it("陈旧数据（距今远超阈值）展示 stale 徽标与延迟天数", async () => {
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await screen.findByTestId("cockpit-stub");
		expect(await screen.findByText(/数据延迟 \d+ 天/)).toBeInTheDocument();
	});
});

describe("InstrumentHubPage overlays", () => {
	it("sends exact Selection and technical identities to the Research Agent route", () => {
		render(
			<InstrumentPageOverlays
				active="send-research"
				instrumentId="2001724"
				onAddWatchlist={() => undefined}
				onClose={() => undefined}
				selectionRunId="selection-run:sha256:selection"
				technicalSnapshotId="technical-analysis:sha256:technical"
			/>,
		);

		expect(screen.getByText("technical-analysis:sha256:technical")).toBeInTheDocument();
		expect(screen.getByText("selection-run:sha256:selection")).toBeInTheDocument();
		const link = screen.getByRole("link", { name: "打开 Research Agent" });
		expect(link).toHaveAttribute("href", expect.stringContaining("/research/agent?"));
		expect(link).toHaveAttribute("href", expect.stringContaining("contextType=instrument"));
		expect(link).toHaveAttribute("href", expect.stringContaining("contextId=technical-analysis%3Asha256%3Atechnical"));
	});

	it("constrains the technical tab to the object-hub viewport so its evidence remains scrollable", () => {
		render(<InstrumentHubPage search={{ selectionRunId: "selection-run:sha256:run-one", tab: "technical" }} />, {
			wrapper: createWrapper(),
		});
		expect(screen.getByRole("tabpanel", { name: "技术证据" })).toHaveClass("h-full", "min-h-0", "overflow-hidden");
	});

	it("can add the exact instrument identity to the local watchlist", async () => {
		const user = userEvent.setup();
		render(<InstrumentHubPage />, { wrapper: createWrapper() });
		await user.click(screen.getByRole("button", { name: "加入自选" }));
		expect(screen.getByRole("dialog", { name: "加入自选" })).toHaveTextContent("1000001");
		await user.click(screen.getByRole("button", { name: "确认加入本机自选" }));
		expect(localStorage.getItem("ditto.market-watchlist.v1")).toBe("[1000001]");
	});
});
