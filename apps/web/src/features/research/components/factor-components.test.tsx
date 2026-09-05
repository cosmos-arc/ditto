import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { researchHandlers } from "@/mocks/handlers/research";
import { server } from "@/mocks/server";
import { FactorAnalysisView } from "./factor-analysis-view";
import { FactorDetailHeader } from "./factor-detail-header";
import { FactorOverview } from "./factor-overview";

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

describe("FactorDetailHeader", () => {
	it("渲染因子名称", async () => {
		render(<FactorDetailHeader id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量因子")).resolves.toBeInTheDocument();
	});

	it("显示因子类型", async () => {
		render(<FactorDetailHeader id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("技术面")).resolves.toBeInTheDocument();
	});

	it("显示 IC 和 IR 指标", async () => {
		render(<FactorDetailHeader id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/0.052/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/0.85/)).resolves.toBeInTheDocument();
	});
});

describe("FactorAnalysisView", () => {
	it("渲染因子分析", async () => {
		render(<FactorAnalysisView id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("IC 时序")).resolves.toBeInTheDocument();
	});

	it("显示 IC 数据", async () => {
		render(<FactorAnalysisView id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/0.058/)).resolves.toBeInTheDocument();
	});

	it("显示行业暴露数据", async () => {
		render(<FactorAnalysisView id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("科技")).resolves.toBeInTheDocument();
	});
});

describe("FactorOverview", () => {
	it("渲染因子属性区域", async () => {
		render(<FactorOverview id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("因子属性")).resolves.toBeInTheDocument();
	});

	it("显示因子元数据", async () => {
		render(<FactorOverview id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("衰减")).resolves.toBeInTheDocument();
		await expect(screen.findByText("换手率")).resolves.toBeInTheDocument();
	});

	it("渲染诊断检查", async () => {
		render(<FactorOverview id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("诊断检查")).resolves.toBeInTheDocument();
		await expect(screen.findByText("衰减测试")).resolves.toBeInTheDocument();
	});

	it("显示诊断结果", async () => {
		render(<FactorOverview id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/pass/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/warning/)).resolves.toBeInTheDocument();
	});
});
