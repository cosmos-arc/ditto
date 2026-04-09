import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { researchHandlers } from "@/mocks/handlers/research";

import { ResearchPulseStrip } from "./research-pulse-strip";
import { FactorTable } from "./factor-table";
import { RecentRuns } from "./recent-runs";
import { ExperimentQueue } from "./experiment-queue";

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
