import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { researchHandlers } from "@/mocks/handlers/research";
import { server } from "@/mocks/server";
import { ExperimentListPage } from "./experiment-list-page";
import { ExperimentQueue } from "./experiment-queue";
import { FactorListPage } from "./factor-list-page";
import { FactorTable } from "./factor-table";
import { RecentRuns } from "./recent-runs";
import { ResearchPage } from "./research-page";
import { ResearchPulseStrip } from "./research-pulse-strip";
import { UniverseListPage } from "./universe-list-page";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		Link: ({
			to,
			params,
			children,
			className,
		}: {
			readonly to: string;
			readonly params?: Readonly<Record<string, string>>;
			readonly children: ReactNode;
			readonly className?: string;
		}) => (
			<a href={params?.["id"] ? to.replace("$id", params["id"]) : to} className={className}>
				{children}
			</a>
		),
	};
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

beforeEach(() => server.use(...researchHandlers));

describe("Research route page contract handoffs", () => {
	it("live 模式渲染 frozen R3 research resources", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<ResearchPage />, { wrapper: createWrapper() });

		expect(screen.queryByText(/prototype only/i)).not.toBeInTheDocument();
		await expect(screen.findByRole("region", { name: "因子监控" })).resolves.toBeInTheDocument();
		expect(screen.getByText("近期运行")).toBeInTheDocument();
		expect(screen.getAllByText("审查队列").length).toBeGreaterThanOrEqual(1);
	});

	it("covers ResearchPage route composition", async () => {
		render(<ResearchPage />, { wrapper: createWrapper() });

		await expect(screen.findByRole("region", { name: "因子监控" })).resolves.toBeInTheDocument();
		expect(screen.getByText("近期运行")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "新建实验" })).toBeInTheDocument();
	});

	it("covers FactorListPage route composition", async () => {
		render(<FactorListPage />, { wrapper: createWrapper() });

		await expect(screen.findByRole("region", { name: "受控因子目录" })).resolves.toBeInTheDocument();
		expect(screen.getByRole("searchbox", { name: "搜索因子" })).toBeInTheDocument();
		expect(screen.getByRole("complementary", { name: "因子详情" })).toBeInTheDocument();
	});

	it("covers ExperimentListPage route composition", () => {
		render(<ExperimentListPage />, { wrapper: createWrapper() });

		expect(screen.getByText("实验队列")).toBeInTheDocument();
		expect(screen.getByText("Experiments")).toBeInTheDocument();
		expect(screen.getByText("Run Detail")).toBeInTheDocument();
	});

	it("covers UniverseListPage route composition", async () => {
		render(<UniverseListPage />, { wrapper: createWrapper() });

		expect(await screen.findByRole("region", { name: "受控股票池目录" })).toBeInTheDocument();
		expect(screen.getByText("股票池目录")).toBeInTheDocument();
		expect(screen.getByText("Universes")).toBeInTheDocument();
		expect(screen.getByRole("complementary", { name: "股票池详情" })).toBeInTheDocument();
	});
});

describe("ResearchPulseStrip", () => {
	it("渲染 4 个脉动指标", async () => {
		render(<ResearchPulseStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("活跃因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("衰减因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("失败因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("审核队列")).resolves.toBeInTheDocument();
	});

	it("显示正确的数值", async () => {
		render(<ResearchPulseStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText(/42/)).resolves.toBeInTheDocument();
	});
});

describe("FactorTable", () => {
	it("渲染因子监控标题", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("因子监控")).resolves.toBeInTheDocument();
	});

	it("显示因子列表", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("动量因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("价值因子")).resolves.toBeInTheDocument();
	});
});

describe("RecentRuns", () => {
	it("渲染近期运行标题", async () => {
		render(<RecentRuns />, { wrapper: createWrapper() });

		await expect(screen.findByText("近期运行")).resolves.toBeInTheDocument();
	});

	it("显示运行列表", async () => {
		render(<RecentRuns />, { wrapper: createWrapper() });

		await expect(screen.findByText("动量策略 v3 回测")).resolves.toBeInTheDocument();
	});
});

describe("ExperimentQueue", () => {
	it("渲染实验标题", async () => {
		render(<ExperimentQueue />, { wrapper: createWrapper() });

		await expect(screen.findByText("实验")).resolves.toBeInTheDocument();
	});

	it("渲染审核队列标题", async () => {
		render(<ExperimentQueue />, { wrapper: createWrapper() });

		await expect(screen.findByText("审核队列")).resolves.toBeInTheDocument();
	});

	it("显示审核项目", async () => {
		render(<ExperimentQueue />, { wrapper: createWrapper() });

		await expect(screen.findByText("情绪因子 v2")).resolves.toBeInTheDocument();
	});
});
