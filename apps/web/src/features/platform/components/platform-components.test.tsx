import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { platformHandlers } from "@/mocks/handlers/platform";

import { HealthStrip } from "./health-strip";
import { ProviderTable } from "./provider-table";
import { PipelineTable } from "./pipeline-table";
import { AlertList } from "./alert-list";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const queryClient = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	server.use(...platformHandlers);
});

describe("HealthStrip", () => {
	it("渲染 4 个健康指标", async () => {
		render(<HealthStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("数据新鲜度")).resolves.toBeInTheDocument();
		await expect(screen.findByText("数据完整性")).resolves.toBeInTheDocument();
		await expect(screen.findByText("数据准确性")).resolves.toBeInTheDocument();
		await expect(screen.findByText("运行任务")).resolves.toBeInTheDocument();
	});

	it("显示正确的健康数值", async () => {
		render(<HealthStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText(/98\.5%/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/99\.2%/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/97\.8%/)).resolves.toBeInTheDocument();
	});
});

describe("ProviderTable", () => {
	it("渲染 Data Providers 标题", async () => {
		render(<ProviderTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("Data Providers")).resolves.toBeInTheDocument();
	});

	it("显示 3 个数据提供者", async () => {
		render(<ProviderTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("tushare")).resolves.toBeInTheDocument();
		await expect(screen.findByText("MiniQMT")).resolves.toBeInTheDocument();
		await expect(screen.findByText("FRED")).resolves.toBeInTheDocument();
	});

	it("显示提供者状态", async () => {
		render(<ProviderTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("45ms")).resolves.toBeInTheDocument();
	});
});

describe("PipelineTable", () => {
	it("渲染 Pipelines 标题", async () => {
		render(<PipelineTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("Pipelines & Jobs")).resolves.toBeInTheDocument();
	});

	it("显示管道列表", async () => {
		render(<PipelineTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("A股日线同步")).resolves.toBeInTheDocument();
		await expect(screen.findByText("分钟线采集")).resolves.toBeInTheDocument();
		await expect(screen.findByText("财务数据更新")).resolves.toBeInTheDocument();
	});

	it("显示管道记录数", async () => {
		render(<PipelineTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("5,200 条")).resolves.toBeInTheDocument();
	});
});

describe("AlertList", () => {
	it("渲染 System Alerts 标题", async () => {
		render(<AlertList />, { wrapper: createWrapper() });

		await expect(screen.findByText("System Alerts")).resolves.toBeInTheDocument();
	});

	it("显示活跃告警", async () => {
		render(<AlertList />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("FRED 数据源连接超时"),
		).resolves.toBeInTheDocument();
	});

	it("过滤掉非活跃告警", async () => {
		render(<AlertList />, { wrapper: createWrapper() });

		expect(screen.queryByText("财务数据定时更新完成")).not.toBeInTheDocument();
	});
});
