import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
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
	it("渲染行情数据区域", async () => {
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("日线证据")).resolves.toBeInTheDocument();
	});

	it("显示精确 as-of 与 K 线数据", async () => {
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("2026-03-10")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/1750/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/快照标识未由接口提供/)).resolves.toBeInTheDocument();
	});

	it("显示成交量", async () => {
		render(<InstrumentChartView id="1000001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/3,210,000/)).resolves.toBeInTheDocument();
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
